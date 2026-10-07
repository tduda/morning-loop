# Morning Loop unattended pre-run: the Windows pendant of run-prep.template.sh (macOS/launchd).
# Runs the read-only SENSE + PLAN half of /morning and writes today's plan file.
# Does NOT dispatch and never performs a never_auto external action: that stays interactive
# (the morning gate). Register it with scripts/register-prep-task.template.ps1, which sets up two
# tasks: MorningLoop-Prep (weekdays 07:52, unconditional) and MorningLoop-Catchup (-IfMissing,
# at logon and every 15 minutes 07:45 to 12:00 on weekdays).
#
# Parity with the macOS runner: -IfMissing catch-up guard, atomic lock, network gate,
# keep-awake for the run, wall-clock-aware watchdog that does not count sleep, delivery safety
# net, named failure classes with an alert, brief-update safety net, on-time record. Each of
# those was paid for by a real failed morning on the macOS side; keep them in step with it.
#
# Written for Windows PowerShell 5.1 (what Task Scheduler runs by default). No PS7-only syntax:
# no `??`, no ternary, no `&&` / `||` pipeline chains.
#
# Copy to scripts/run-prep.ps1 (gitignored), fill the FILL lines, then do ONE supervised run:
#     powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-prep.ps1; "exit $LASTEXITCODE"
# before you hand it to Task Scheduler. See scripts/SETUP-DELIVERY.md, "Scheduling the run (Windows)".
#
# Modes:
#   (no switch)  an unconditional run. Used by the 07:52 task and by a human running it by hand.
#   -IfMissing   catch-up mode. Exits 0 silently unless it is a weekday, local time 07:45 to
#                12:00, and today's receipt does not record a delivered brief.
#
# Exit codes (Task Scheduler shows them as "Last Run Result"; a health check reads them):
#   0   plan written and brief delivered (or a catch-up tick that found nothing owed)
#   2   another run holds the lock: skipped, no race
#   3   the client ran but wrote no plan file
#   4   plan written but the brief never reached a channel
#   10  optional VPN gate: VPN never came up, nothing attempted (the catch-up retries)
#   75  no network at fire time, nothing attempted (the catch-up retries)
#   124 the watchdog stopped the client after its awake-time budget
#
# Env knobs (all optional):
#   MORNING_WATCHDOG_SECS   awake-time budget for the run, default 3000 (50 min)
#   MORNING_NET_HOST        host the network gate probes on 443, default api.anthropic.com
#   MORNING_NET_WAIT_SECS / MORNING_NET_STEP_SECS   network gate limits, default 300 / 10
#   MORNING_VPN_WAIT_SECS   optional VPN gate limit, default 1200
#   MORNING_NO_ALERT=1      skip the toast notifications (receipts and log lines still written)
#   MORNING_NOW             'yyyy-MM-dd HH:mm' to pin "now" for the -IfMissing guard and today's
#                           date. For testing the guard only; never set it in the task.
#   MORNING_RUNNER_LIB=1    dot-source the script to load its functions without running it (tests)
param([switch]$IfMissing)

# ---------------------------------------------------------------------------------------------
# FILL: absolute paths only. Task Scheduler runs with a minimal environment and no profile.
# ---------------------------------------------------------------------------------------------
$WorkDir    = "<PATH TO YOUR WORKSPACE>"                              # FILL: the folder you ran setup.py on
$Claude     = "$env:USERPROFILE\.local\bin\claude.exe"                # FILL if claude lives elsewhere
$Python     = "python"                                                # FILL if python is not on the task's PATH
$Config     = ""                                                      # optional: absolute path of your morning/config.yml, if it lives elsewhere
$TaskName   = "MorningLoop-Prep"                                      # must match register-prep-task.ps1

# Optional: connector tools the unattended run may call without asking. None by default; with
# none listed the run still finishes, with a thinner brief (an unapproved connector call is
# denied, not prompted). READ-ONLY tools only, by full name mcp__<server>__<tool>. Never
# "mcp__<server>" or "mcp__<server>__*": those approve write tools too, in a run that reads
# inbox and chat, which anyone can write into.
$AllowedConnectorTools = @(
    # "mcp__atlassian__getJiraIssue"               # examples only: tool names
    # "mcp__atlassian__searchJiraIssuesUsingJql"   # differ by server, check yours
)

# Optional VPN gate. Internal MCP sources (Jira/Confluence on a lab network) may only resolve
# inside a VPN. Leave both empty to skip the check entirely.
$VpnProbeHost = ""      # e.g. "gitlab.example.lab": a hostname that only resolves on VPN
$VpnProfile   = ""      # e.g. "Office VPN": the rasdial profile name to reconnect with
# ---------------------------------------------------------------------------------------------

# ============================================================================================
# FUNCTIONS. Pure where possible, so the guard, the receipt shape, the watchdog arithmetic and
# the failure classifier can be exercised off Windows (MORNING_RUNNER_LIB=1).
# ============================================================================================
function Join-P {
    # Path.Combine(params string[]) exists on .NET Framework 4, so this works on 5.1 and 7.
    [IO.Path]::Combine([string[]]$args)
}

function Get-EngineAllowedTools([string]$ConfigFile) {
    # One Bash rule per engine script /morning calls, with the interpreter setup.py wrote to
    # owner.python, so engine calls don't stall on a permission prompt on a fresh account. No
    # MCP wildcard: Claude Code ignores a bare "mcp__*", and "mcp__<server>" would pre-approve
    # that server's write tools too, in a run that reads text anyone can write into.
    $py = 'python3'
    if ($ConfigFile -and (Test-Path -LiteralPath $ConfigFile)) {
        $m = Select-String -LiteralPath $ConfigFile -Pattern '^  python:\s*([^#]*)' | Select-Object -First 1
        if ($m -and $m.Matches[0].Groups[1].Value.Trim()) { $py = $m.Matches[0].Groups[1].Value.Trim() }
    }
    foreach ($s in 'asks', 'coach', 'doctor', 'notify', 'onboard', 'ontime', 'reconcile_ledger',
                   'sharpen', 'shipped', 'tickets', 'trust') {
        "Bash($py morning/engine/$s.py *)"
    }
}

function Test-IsWindows {
    # $IsWindows is PS6+. This form also works on Windows PowerShell 5.1.
    [Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
}

function Get-NowLocal {
    if ($env:MORNING_NOW) {
        return [datetime]::ParseExact($env:MORNING_NOW, 'yyyy-MM-dd HH:mm', [Globalization.CultureInfo]::InvariantCulture)
    }
    Get-Date
}

function Get-Stamp { (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') }

function Get-IsoStamp { (Get-Date).ToString('yyyy-MM-ddTHH:mm:sszzz') }

$script:Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Write-RunLog([string]$Line) {
    # UTF-8 without a BOM, one write per line. Add-Content in 5.1 writes the ANSI code page and
    # Out-File -Encoding utf8 writes a BOM on a new file, and ontime.py anchors its regexes at
    # the start of a line, so a BOM in front of the first "starting" line would hide that run.
    [IO.File]::AppendAllText($script:Log, $Line + "`r`n", $script:Utf8NoBom)
}

function ConvertTo-JsonText([string]$s) {
    if ($null -eq $s) { return 'null' }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('"')
    foreach ($ch in $s.ToCharArray()) {
        $code = [int]$ch
        if     ($ch -eq '"')  { [void]$sb.Append('\"') }
        elseif ($ch -eq '\')  { [void]$sb.Append('\\') }
        elseif ($code -eq 10) { [void]$sb.Append('\n') }
        elseif ($code -eq 13) { [void]$sb.Append('\r') }
        elseif ($code -eq 9)  { [void]$sb.Append('\t') }
        elseif ($code -lt 32) { [void]$sb.Append(('\u{0:x4}' -f $code)) }
        else                  { [void]$sb.Append($ch) }
    }
    [void]$sb.Append('"')
    $sb.ToString()
}

function Write-ReceiptFile([string]$Path, $Fields) {
    # Hand-built rather than ConvertTo-Json: 5.1 emits `"key":  "value"` (two spaces) and other
    # tools, and humans, grep receipts for `"status": "sent"`. Same shape as the macOS runner's
    # printf receipts: date, status, stage, error|detail, checked_at.
    $parts = @()
    foreach ($k in $Fields.Keys) { $parts += ('  "{0}": {1}' -f $k, (ConvertTo-JsonText ([string]$Fields[$k]))) }
    $text = "{`n" + ($parts -join ",`n") + "`n}`n"
    [IO.Directory]::CreateDirectory((Split-Path -Parent $Path)) | Out-Null
    [IO.File]::WriteAllText($Path, $text, $script:Utf8NoBom)
}

function New-FailedReceipt([string]$Date, [string]$Stage, [string]$ErrorText) {
    $f = New-Object System.Collections.Specialized.OrderedDictionary
    $f['date'] = $Date; $f['status'] = 'failed'; $f['stage'] = $Stage
    $f['error'] = $ErrorText; $f['checked_at'] = (Get-IsoStamp)
    $f
}

function Get-ReceiptText([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return '' }
    try { [IO.File]::ReadAllText($Path) } catch { '' }
}

function Test-Delivered([string]$ReceiptFile) {
    # `sent` covers mattermost (and macos elsewhere). `rendered_not_sent` is channel `file`, the
    # Windows default: the page exists, so the brief is done. Counting only `sent` would make the
    # catch-up re-run the whole prep every 15 minutes until noon for every file-channel adopter.
    (Get-ReceiptText $ReceiptFile) -match '"status":\s*"(sent|rendered_not_sent)"'
}

function Get-ReceiptStage([string]$ReceiptFile) {
    $m = [regex]::Match((Get-ReceiptText $ReceiptFile), '"stage":\s*"([^"]*)"')
    if ($m.Success) { return $m.Groups[1].Value }
    ''
}

function Test-BriefOwed([datetime]$Now, [string]$ReceiptFile) {
    # The -IfMissing guard. Weekdays only, the morning window only, and only while today's
    # receipt does not record a delivery. Checks the RECEIPT, not the plan file: a plan file
    # with a failed delivery is still an undelivered brief.
    if ($Now.DayOfWeek -eq [DayOfWeek]::Saturday -or $Now.DayOfWeek -eq [DayOfWeek]::Sunday) { return $false }
    $hhmm = $Now.Hour * 100 + $Now.Minute
    if ($hhmm -lt 745 -or $hhmm -gt 1200) { return $false }
    -not (Test-Delivered $ReceiptFile)
}

function Get-WatchdogTick([double]$GapSecs, [int]$TickSecs) {
    # A tick that took far longer than it should means the machine slept; that gap is reported
    # and NOT counted against the awake-time budget. Same threshold as the macOS runner.
    $slept = $GapSecs -gt ($TickSecs * 4 + 60)
    New-Object PSObject -Property @{ Slept = $slept; SleptMin = [int][math]::Floor($GapSecs / 60); AwakeAdd = $(if ($slept) { 0 } else { $GapSecs }) }
}

function Get-SleptMinutes([string]$RunLog) {
    $sum = 0
    foreach ($m in [regex]::Matches($RunLog, '(?m)^watchdog: machine slept for about (\d+) min')) { $sum += [int]$m.Groups[1].Value }
    $sum
}

function Get-FailureClass([string]$RunLog, [int]$Status, [int]$SleptMin, [bool]$TimedOut, [int]$BudgetMin) {
    # Diagnose WHY from what claude actually said, because "it didn't run" is useless and
    # "your login expired" is actionable. Reads ONLY this run's slice of the log: grepping the
    # whole cumulative log once reported every later failure as a login expiry, forever.
    # Order matters: the more specific causes win.
    $o = [Text.RegularExpressions.RegexOptions]::IgnoreCase
    if ($SleptMin -gt 0 -or [regex]::IsMatch($RunLog, 'went to sleep|Connection closed mid-response', $o)) {
        return @('The machine slept mid-run', "Windows went to sleep before the run finished ($SleptMin min asleep). Check the power plan allows the task to keep the machine awake, then run /morning.")
    }
    if ([regex]::IsMatch($RunLog, 'Failed to authenticate|OAuth session expired|Invalid API key|Please run.*login', $o)) {
        return @('Claude login expired', "Run: claude /login in a terminal, then /morning to get today's brief.")
    }
    if ([regex]::IsMatch($RunLog, "ENOTFOUND|EAI_AGAIN|Can't reach the API server|getaddrinfo|Could not resolve host|Network is unreachable|No such host is known", $o)) {
        # The network gate only lets a run start with a network, so reaching this means the
        # network went away DURING the run.
        return @('Lost the network mid-run', 'The run started with a network and then lost it, so the API became unreachable. The catch-up will retry once it has a network.')
    }
    if ([regex]::IsMatch($RunLog, 'mcp.*timeout|mcp.*timed out|sse.*closed|sse.*disconnected|sse.*timeout|event stream.*closed|event stream.*ended|econnreset|connection reset by peer', $o)) {
        return @('An MCP server dropped mid-run (SSE/stream timeout)', "A tool server's stream died, so the run could not finish. Re-run /morning manually; if it recurs, reconnect that MCP server.")
    }
    if ($TimedOut) {
        return @("The run timed out ($BudgetMin min awake)", 'The watchdog stopped the client before it wrote a plan. Likely a hang on a network or MCP source; run /morning manually.')
    }
    if ($Status -ne 0) {
        return @("The prep run failed (exit $Status)", 'No brief today. Check runner.log, then run /morning manually.')
    }
    @('No plan file was written', 'The run finished but produced nothing. Check runner.log.')
}

function Show-Alert([string]$Title, [string]$Text) {
    # One-line Windows balloon/toast. WinForms NotifyIcon needs no install, only .NET (built in).
    # A failure here is logged, never fatal. No-op off Windows and under MORNING_NO_ALERT=1.
    if ($env:MORNING_NO_ALERT -eq '1' -or -not (Test-IsWindows)) { return }
    try {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        # Types by name, not as [literals]: PowerShell resolves a type literal when it compiles
        # the function, which off Windows throws even though this branch never runs there.
        $t = New-Object -TypeName 'System.Windows.Forms.NotifyIcon'
        $t.Icon = ('System.Drawing.SystemIcons' -as [type])::Warning
        $t.Visible = $true
        $t.BalloonTipTitle = $Title
        $t.BalloonTipText  = $Text
        $t.ShowBalloonTip(15000)
        Start-Sleep -Seconds 2
        $t.Dispose()
    } catch {
        Write-RunLog "NOTIFY: toast failed ($_)"
    }
}

function Set-KeepAwake([bool]$On) {
    # SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED) holds off IDLE sleep for as long
    # as this thread lives; ES_CONTINUOUS alone clears it. HONEST LIMIT, as on macOS: it does not
    # stop a lid close, a user-initiated sleep, or a battery policy, so a laptop with the lid shut
    # still sleeps. No-op off Windows.
    if (-not (Test-IsWindows)) { return }
    try {
        if (-not ('MorningLoop.Power' -as [type])) {
            Add-Type -Namespace MorningLoop -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
        }
        $flags = [uint32]2147483648                  # ES_CONTINUOUS 0x80000000
        if ($On) { $flags = [uint32]2147483649 }     # | ES_SYSTEM_REQUIRED 0x00000001
        $power = 'MorningLoop.Power' -as [type]
        [void]$power::SetThreadExecutionState($flags)
    } catch {
        Write-RunLog "keep-awake: SetThreadExecutionState failed ($_), continuing without it"
    }
}

function Test-NetUp([string]$HostName) {
    # Real resolve plus a real TCP connect on 443, bounded at 4 seconds, the same path the API
    # client takes.
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $ar = $c.BeginConnect($HostName, 443, $null, $null)
        if (-not $ar.AsyncWaitHandle.WaitOne(4000)) { return $false }
        $c.EndConnect($ar)
        return $c.Connected
    } catch { return $false } finally { $c.Close() }
}

function Get-NetCause([string]$HostName) {
    try { [void][System.Net.Dns]::GetHostAddresses($HostName); "DNS resolves but port 443 is unreachable" }
    catch { "DNS does not resolve $HostName" }
}

function Test-Vpn {
    if (-not $VpnProbeHost) { return $true }
    try { [void][System.Net.Dns]::GetHostAddresses($VpnProbeHost); return $true }
    catch { return $false }
}

function Read-LogFrom([long]$Offset) {
    # This run's slice of the cumulative log, by byte offset taken before the run started.
    try {
        $fs = [IO.File]::Open($script:Log, 'Open', 'Read', 'ReadWrite')
        try {
            [void]$fs.Seek([math]::Min($Offset, $fs.Length), 'Begin')
            $sr = New-Object IO.StreamReader($fs, $script:Utf8NoBom)
            $sr.ReadToEnd()
        } finally { $fs.Close() }
    } catch { '' }
}

function Stop-ClientTree([int]$ClientPid) {
    # claude spawns node and MCP children; killing only the parent orphans them.
    if (Test-IsWindows) { & taskkill.exe /PID $ClientPid /T /F 2>&1 | Out-Null }
    else { Stop-Process -Id $ClientPid -Force -ErrorAction SilentlyContinue }
}

function Invoke-Python([string[]]$PyArgs) {
    $out = & $Python @PyArgs 2>&1
    $code = $LASTEXITCODE
    foreach ($l in $out) { Write-RunLog ([string]$l) }
    $code
}

# Tests dot-source the script with this set, to get the functions above without a run.
if ($env:MORNING_RUNNER_LIB -eq '1') { return }

# ============================================================================================
# MAIN
# ============================================================================================
$Automation = Join-P $WorkDir 'morning' 'state'
$PlanDir    = Join-P $WorkDir 'morning' 'briefs'
$script:Log = Join-P $Automation 'runner.log'
$Notifier   = Join-P $WorkDir 'morning' 'engine' 'notify.py'
$Ontime     = Join-P $WorkDir 'morning' 'engine' 'ontime.py'
$Receipts   = Join-P $Automation 'receipts'

try { Set-Location -LiteralPath $WorkDir -ErrorAction Stop } catch { Write-Error "FAILED cd $WorkDir"; exit 1 }
[IO.Directory]::CreateDirectory($Automation) | Out-Null
[IO.Directory]::CreateDirectory($Receipts) | Out-Null

# Python on Windows reads and prints in the ANSI code page unless told otherwise; the brief and
# the log carry emoji and middle dots. ontime.py finds its config by $USER, which Windows does
# not set, so give it USERNAME (and MORNING_CONFIG when the FILL line names a config).
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
if (-not $env:USER) { $env:USER = $env:USERNAME }
if ($Config) { $env:MORNING_CONFIG = $Config }
$env:MORNING_ROOT = $WorkDir
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# The day the run STARTED, not the day it ended: a run that thaws after midnight must not write
# its receipt to the next day.
$Now         = Get-NowLocal
$Today       = $Now.ToString('yyyy-MM-dd')
$PlanFile    = Join-P $PlanDir "$Today.md"
$ReceiptFile = Join-P $Receipts "$Today.json"

# ---------------------------------------------------------------------------------------------
# GUARD. A fixed fire time on a laptop often lands while the machine is asleep or only half
# awake. The fix is to stop treating "it is 07:52" as the trigger and start treating "the
# machine is genuinely awake and a brief is still owed" as the trigger: the catch-up task runs
# this with -IfMissing at logon and every 15 minutes, and this is the silent exit almost every
# tick takes. It must be cheap and must not touch the log.
# ---------------------------------------------------------------------------------------------
if ($IfMissing -and -not (Test-BriefOwed $Now $ReceiptFile)) { exit 0 }

# ---------------------------------------------------------------------------------------------
# LOCK. A scheduled trigger, the catch-up and a manual run all target the same plan file,
# run-log and receipt. The lock is a directory holding a `pid` file opened with CreateNew, which
# the filesystem makes atomic: exactly one opener wins, there is no check-then-write window.
# A lock whose pid is gone is stale (a killed run leaves one) and gets reclaimed once.
# ---------------------------------------------------------------------------------------------
$LockDir = Join-P $Automation '.run.lock'
$LockPid = Join-P $LockDir 'pid'
function Get-Lock {
    [IO.Directory]::CreateDirectory($LockDir) | Out-Null
    try {
        $fs = [IO.File]::Open($LockPid, 'CreateNew', 'Write', 'Read')
        $b = $script:Utf8NoBom.GetBytes([string]$PID)
        $fs.Write($b, 0, $b.Length); $fs.Close()
        return $true
    } catch { return $false }
}
if (-not (Get-Lock)) {
    $Holder = ''
    try { $Holder = ([IO.File]::ReadAllText($LockPid)).Trim() } catch { $Holder = "" }
    if ($Holder -match '^\d+$' -and (Get-Process -Id ([int]$Holder) -ErrorAction SilentlyContinue)) {
        Write-RunLog "===== $(Get-Stamp) skipped: a run is already in progress (pid $Holder) ====="
        exit 2
    }
    $Shown = $Holder; if (-not $Shown) { $Shown = 'unknown' }
    Write-RunLog "===== $(Get-Stamp) reclaiming stale lock (pid $Shown is gone) ====="
    Remove-Item -LiteralPath $LockDir -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Get-Lock)) { exit 2 }
}

try {
    Set-KeepAwake $true   # held for the network wait and the whole run; cleared in finally

    # -----------------------------------------------------------------------------------------
    # NETWORK GATE. Wait for the network before launching the run, bounded by WALL CLOCK (a
    # sleeping machine suspends this loop too, so the deadline is read from the clock, not
    # counted). A run that starts without a network burns its budget on DNS and then reports a
    # generic failure that names no cause. If it never comes up: one log line, a failed receipt
    # with stage "no network at fire time", one toast per day for this cause (a 15-minute
    # catch-up must not ring every 15 minutes), and exit 75. This runs BEFORE the "starting"
    # line, so a gate miss never opens a runner block.
    # -----------------------------------------------------------------------------------------
    $NetHost = 'api.anthropic.com'; if ($env:MORNING_NET_HOST) { $NetHost = $env:MORNING_NET_HOST }
    $NetWait = 300; if ($env:MORNING_NET_WAIT_SECS) { $NetWait = [int]$env:MORNING_NET_WAIT_SECS }
    $NetStep = 10;  if ($env:MORNING_NET_STEP_SECS) { $NetStep = [int]$env:MORNING_NET_STEP_SECS }
    $NetT0 = Get-Date
    $NetDeadline = $NetT0.AddSeconds($NetWait)
    while (-not (Test-NetUp $NetHost)) {
        if ((Get-Date) -ge $NetDeadline) {
            if (Test-NetUp $NetHost) { break }   # one last try after a thaw past the deadline
            $Cause  = Get-NetCause $NetHost
            $Waited = [int]((Get-Date) - $NetT0).TotalSeconds
            Write-RunLog "===== $(Get-Stamp) no network at fire time: $Cause after waiting ${Waited}s (limit ${NetWait}s). Not starting the run; the catch-up retries on its next tick. ====="
            if (-not (Test-Delivered $ReceiptFile)) {
                $PriorStage = Get-ReceiptStage $ReceiptFile
                Write-ReceiptFile $ReceiptFile (New-FailedReceipt $Today 'no network at fire time' "$Cause after waiting ${Waited}s. The machine was probably asleep or on a network that was not up yet. The catch-up retries every 15 minutes.")
                if ($PriorStage -ne 'no network at fire time') {
                    Show-Alert 'Morning brief waiting for network' "$Cause. The catch-up will retry once there is a network."
                }
            }
            [void](Invoke-Python @($Ontime, '--root', $WorkDir, '--launchd-log', $script:Log, 'record', '--date', $Today))
            exit 75
        }
        Start-Sleep -Seconds $NetStep
    }
    $NetWaited = [int]((Get-Date) - $NetT0).TotalSeconds
    if ($NetWaited -gt 0) { Write-RunLog "===== $(Get-Stamp) network up after ${NetWaited}s =====" }

    # Optional VPN gate, kept from an earlier Windows runner: internal sources may only resolve
    # on the VPN. Same shape as the network gate: before the starting line, wall-clock bounded,
    # a failed receipt with a named stage, one toast per day, exit 10.
    if (-not (Test-Vpn)) {
        Write-RunLog "VPN down at start: trying rasdial reconnect"
        if ($VpnProfile) { foreach ($l in (& rasdial $VpnProfile 2>&1)) { Write-RunLog ([string]$l) } }
        $VpnWait = 1200; if ($env:MORNING_VPN_WAIT_SECS) { $VpnWait = [int]$env:MORNING_VPN_WAIT_SECS }
        $VpnDeadline = (Get-Date).AddSeconds($VpnWait)
        while (-not (Test-Vpn) -and (Get-Date) -lt $VpnDeadline) { Start-Sleep -Seconds 30 }
        if (-not (Test-Vpn)) {
            Write-RunLog "===== $(Get-Stamp) VPN down at fire time: $VpnProbeHost does not resolve after ${VpnWait}s. Not starting the run; the catch-up retries on its next tick. ====="
            if (-not (Test-Delivered $ReceiptFile)) {
                $PriorStage = Get-ReceiptStage $ReceiptFile
                Write-ReceiptFile $ReceiptFile (New-FailedReceipt $Today 'VPN down at fire time' "$VpnProbeHost did not resolve after ${VpnWait}s. Connect the VPN; the catch-up retries every 15 minutes.")
                if ($PriorStage -ne 'VPN down at fire time') { Show-Alert 'Morning brief waiting for VPN' 'Connect the VPN; the catch-up will retry.' }
            }
            [void](Invoke-Python @($Ontime, '--root', $WorkDir, '--launchd-log', $script:Log, 'record', '--date', $Today))
            exit 10
        }
        Write-RunLog "VPN up, continuing"
    }

    $ModeNote = ''
    if ($IfMissing) { $ModeNote = " (catch-up: no delivered brief for $Today yet)" }
    Write-RunLog "===== $(Get-Stamp) starting /morning --prep$ModeNote ====="

    # Where this run's slice of the cumulative log starts, so the classifier reads only THIS run.
    $LogStart = (Get-Item -LiteralPath $script:Log).Length

    $ExitCode = $null
    $TimedOut = $false
    $WdBudget = 3000; if ($env:MORNING_WATCHDOG_SECS) { $WdBudget = [int]$env:MORNING_WATCHDOG_SECS }

    if ($IfMissing -and (Test-Path -LiteralPath $PlanFile)) {
        # A catch-up tick that finds today's plan already written but not delivered: deliver it
        # rather than re-running sense+plan, which would re-hit Jira/Confluence for nothing and
        # could overwrite a plan you are already acting on. The safety net below delivers it.
        Write-RunLog "SKIP: plan file for $Today already exists, delivering it instead of re-running sense+plan"
        $ExitCode = 0
    } else {
        # --print: headless single-shot. acceptEdits lets it write the plan file without a prompt;
        # --allowedTools pre-approves the engine calls (see Get-EngineAllowedTools).
        $TmpOut = Join-P $Automation 'claude-prep-out.tmp'
        $TmpErr = Join-P $Automation 'claude-prep-err.tmp'

        # Self-identify. routine_health sweeps Get-ScheduledTask and sees this very task as
        # State=Running with LastRunTime = now, which looks like a competing instance to a model
        # that knows about past race incidents. Tell it that only a skipped line in the log is a
        # real race.
        $PrepPrompt = '/morning --prep' +
          ' [SCHEDULED RUN] You are executing INSIDE the Windows scheduled task' +
          " $TaskName (wrapper PID $PID, started $(Get-Date -Format 'HH:mm:ss'))." +
          ' During routine_health that task WILL show State=Running with LastRunTime = this run.' +
          ' That is you. Never abort, wait, or skip because of it. Only a SECOND run-prep wrapper' +
          ' (a skipped-because-a-run-is-in-progress line in runner.log) is a real race.'

        $Allowed = @(Get-EngineAllowedTools (Join-P $WorkDir 'morning' 'config.yml')) + @($AllowedConnectorTools)
        Write-RunLog "permissions: $($Allowed.Count - @($AllowedConnectorTools).Count) engine rules; $(@($AllowedConnectorTools).Count) connector tool(s) pre-approved $($AllowedConnectorTools -join ' ')"
        $ClaudeArgs = @('--print', "`"$PrepPrompt`"", '--permission-mode', 'acceptEdits', '--allowedTools') +
            @($Allowed | ForEach-Object { "`"$_`"" })

        $p = Start-Process -FilePath $Claude -WorkingDirectory $WorkDir `
            -ArgumentList $ClaudeArgs `
            -NoNewWindow -PassThru -RedirectStandardOutput $TmpOut -RedirectStandardError $TmpErr
        # Touch Handle now: on 5.1 a Process from Start-Process -PassThru can otherwise report a
        # null ExitCode after exit, which would turn a total failure into 0x0.
        $null = $p.Handle

        # WALL-CLOCK-AWARE WATCHDOG. Use the Process object's own WaitForExit(ms) per tick, not
        # Wait-Process (which polls externally and leaves ExitCode unreliable). Each tick reads
        # the clock: a tick that took far longer than WdTick means the machine slept, which is
        # logged as `watchdog: machine slept for about N min` and NOT counted against the
        # budget. The budget is AWAKE time. The classifier reads that line, so a run that froze
        # with the machine reports `slept`, never `timeout`, and ontime.py carries the minutes.
        $WdTick = 15
        $Awake = 0.0
        $Last = Get-Date
        while (-not $p.WaitForExit($WdTick * 1000)) {
            $NowT = Get-Date
            $t = Get-WatchdogTick (($NowT - $Last).TotalSeconds) $WdTick
            if ($t.Slept) {
                Write-RunLog "watchdog: machine slept for about $($t.SleptMin) min (wall clock $($Last.ToString('HH:mm:ss')) to $($NowT.ToString('HH:mm:ss'))), not counted against the budget"
            } else { $Awake += $t.AwakeAdd }
            $Last = $NowT
            if ($Awake -ge $WdBudget) {
                Write-RunLog "watchdog: prep exceeded $([int]($WdBudget / 60)) min awake, killing $($p.Id)"
                Stop-ClientTree $p.Id
                $TimedOut = $true
                break
            }
        }
        # The final partial tick can also span a sleep (the client exits right after the thaw).
        $NowT = Get-Date
        $t = Get-WatchdogTick (($NowT - $Last).TotalSeconds) $WdTick
        if ($t.Slept) {
            Write-RunLog "watchdog: machine slept for about $($t.SleptMin) min (wall clock $($Last.ToString('HH:mm:ss')) to $($NowT.ToString('HH:mm:ss'))), not counted against the budget"
        }

        [void]$p.WaitForExit(30000)
        if ($TimedOut) { $ExitCode = 124 }
        elseif ($p.HasExited -and $null -ne $p.ExitCode) { $ExitCode = [int]$p.ExitCode }
        else { $ExitCode = 1 }

        foreach ($f in @($TmpOut, $TmpErr)) {
            if (Test-Path -LiteralPath $f) {
                foreach ($l in [IO.File]::ReadAllLines($f, $script:Utf8NoBom)) { Write-RunLog $l }
                Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue
            }
        }
        Write-RunLog "===== $(Get-Stamp) claude finished (exit $ExitCode) ====="
    }

    # -----------------------------------------------------------------------------------------
    # DELIVERY SAFETY NET (docs/RUN-AND-NOTIFY.md). Phase 2b should deliver the brief itself; this
    # block does not trust that. If today has no delivered receipt, deliver here. Idempotent:
    # notify.py reuses today's brief id, so a brief is never delivered twice.
    #
    # Channel + webhook come from the same untracked file the macOS runner sources:
    #   %USERPROFILE%\.config\morning-loop\notify.env   (lines like: export MORNING_NOTIFY_CHANNEL=mattermost)
    # The webhook is a credential; never inline it here, this script may be committed.
    # -----------------------------------------------------------------------------------------
    $NotifyEnv = Join-P $HOME '.config' 'morning-loop' 'notify.env'
    if (Test-Path -LiteralPath $NotifyEnv) {
        foreach ($raw in (Get-Content -LiteralPath $NotifyEnv)) {
            $line = $raw.Trim() -replace '^export\s+', ''
            if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                Set-Item -Path "Env:$($Matches[1])" -Value ($Matches[2].Trim([char]34, [char]39))
            }
        }
    }
    $Channel = 'file'; if ($env:MORNING_NOTIFY_CHANNEL) { $Channel = $env:MORNING_NOTIFY_CHANNEL }
    if ($Channel -eq 'macos') { $Channel = 'file' }   # no notification center here; the toast covers it
    if ($Channel -eq 'mattermost' -and -not $env:MORNING_MATTERMOST_WEBHOOK) {
        Write-RunLog "DELIVER: MORNING_MATTERMOST_WEBHOOK not set in $NotifyEnv, falling back to channel=file"
        $Channel = 'file'
    }
    $NotifyArgs = @($Notifier, '--root', $WorkDir, '--brief', $PlanFile, '--date', $Today, '--channel', $Channel)
    # notify.py reads MORNING_MATTERMOST_WEBHOOK from this process's environment.

    # alert_on_miss: a failure that only reaches a log file IS a silent failure. Every failure
    # path toasts and writes a `failed` receipt, so tomorrow's HEALTH check can tell "failed for
    # this reason" from "never attempted".
    function Send-AlertOnMiss([string]$Reason, [string]$Detail) {
        Write-RunLog "alert: $Reason - $Detail"
        Show-Alert 'Morning brief did NOT run' "$Reason. $Detail"
        Write-ReceiptFile $ReceiptFile (New-FailedReceipt $Today $Reason $Detail)
    }
    # alert_partial: a watchdog kill mid-pre-draft is NOT a missing brief. Toast WITHOUT
    # overwriting the good receipt, and leave a sidecar for tomorrow's HEALTH check.
    function Send-AlertPartial([string]$Reason, [string]$Detail) {
        Write-RunLog "alert(partial): $Reason - $Detail"
        Show-Alert 'Brief delivered, drafting cut short' "$Reason. $Detail"
        $f = New-Object System.Collections.Specialized.OrderedDictionary
        $f['date'] = $Today; $f['status'] = 'partial'; $f['stage'] = $Reason
        $f['detail'] = $Detail; $f['checked_at'] = (Get-IsoStamp)
        Write-ReceiptFile (Join-P $Receipts "$Today.partial.json") $f
    }

    $RunLog   = Read-LogFrom $LogStart
    $SleptMin = Get-SleptMinutes $RunLog
    $DraftDir = Join-P $WorkDir 'morning' 'drafts' $Today
    $Drafts   = @()
    if (Test-Path -LiteralPath $DraftDir) { $Drafts = @(Get-ChildItem -LiteralPath $DraftDir -Filter '*.md' -File) }

    if ($RunLog -match '(?m)^watchdog: prep exceeded') {
        $NVerified = @($Drafts | Where-Object { Select-String -LiteralPath $_.FullName -Pattern 'VERIFY RESULTS' -SimpleMatch -Quiet }).Count
        if ($SleptMin -gt 0) {
            Send-AlertPartial "The machine slept mid-run ($SleptMin min), then the watchdog stopped it" "$($Drafts.Count) drafts written, $NVerified verified. The brief still says drafting. Run /morning to finish and grade them."
        } else {
            Send-AlertPartial 'Watchdog killed the run' "$($Drafts.Count) drafts written, $NVerified verified. The brief still says drafting. Run /morning to finish and grade them."
        }
        # A watchdog-killed run is otherwise invisible in the run-log evidence trail: Phase 2c
        # never runs, so nothing writes its line. Log it from the runner, the only thing alive.
        $RunLogMd = Join-P $Automation 'run-log.md'
        $Line = "`n- $Today run: **watchdog-killed after $([int]($WdBudget / 60)) min of awake time**, auto-logged by run-prep.ps1 because Phase 2c never ran. Pre-drafted **$($Drafts.Count)** file(s) in ``morning/drafts/$Today/``, **$NVerified** carrying a verify stamp. Brief delivery: see ``delivery-receipts/$Today.json``. This line exists so the run is not invisible in the evidence trail; the qualitative detail is absent because the run was killed before it could write it.`n"
        [IO.File]::AppendAllText($RunLogMd, $Line, $script:Utf8NoBom)
    }

    $Delivered = $false
    if (Test-Delivered $ReceiptFile) {
        Write-RunLog "delivery: already delivered today, nothing to do"
    } elseif (-not (Test-Path -LiteralPath $PlanFile)) {
        $Status = 0; if ($null -ne $ExitCode) { $Status = [int]$ExitCode }
        $Fc = Get-FailureClass $RunLog $Status $SleptMin $TimedOut ([int]($WdBudget / 60))
        Send-AlertOnMiss $Fc[0] $Fc[1]
    } else {
        Write-RunLog "delivery: no delivered receipt for $Today, delivering from the safety net (channel=$Channel)"
        $SendStatus = Invoke-Python $NotifyArgs
        if ($SendStatus -ne 0) {
            Send-AlertOnMiss 'Brief written but delivery failed' "The plan exists but did not reach you. See $ReceiptFile"
        } else { $Delivered = $true }
    }

    # -----------------------------------------------------------------------------------------
    # BRIEF-UPDATE SAFETY NET. Phase 2p should update the brief in place as each draft lands and
    # re-run the notifier. When the watchdog fires mid-drafting it never gets there, and the
    # brief still lists finished drafts as pending to-dos. So: if drafts exist for today and the
    # plan file is OLDER than the newest draft, append a factual index and re-deliver (same
    # date, same id). A file listing, not a summary: the runner cannot read the drafts, and a
    # fabricated summary would be worse than none.
    # -----------------------------------------------------------------------------------------
    if ($Drafts.Count -gt 0 -and (Test-Path -LiteralPath $PlanFile)) {
        $Newest = $Drafts | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
        if ($Newest.LastWriteTimeUtc -gt (Get-Item -LiteralPath $PlanFile).LastWriteTimeUtc) {
            Write-RunLog "brief-update: drafts are newer than the brief, appending the index and re-delivering"
            $sb = New-Object System.Text.StringBuilder
            [void]$sb.Append("`n`n---`n`n## " + [char]::ConvertFromUtf32(0x1F916) + " DRAFTS PRODUCED THIS RUN (appended by run-prep.ps1 at $(Get-Date -Format 'HH:mm'))`n`n")
            [void]$sb.Append("The run was cut short before it could update this section itself, so the list below was`n")
            [void]$sb.Append("written by the runner from the files on disk. Nothing here is sent; each ships only with`n")
            [void]$sb.Append("your yes. Grades come from each file's own verify stamp, and `"not graded`" means exactly`n")
            [void]$sb.Append("that: the draft exists but no independent verifier reached it.`n`n")
            foreach ($d in ($Drafts | Sort-Object Name)) {
                $V = 'not graded'
                $m = Select-String -LiteralPath $d.FullName -Pattern 'Verdict: *([A-Za-z ]*)' | Select-Object -First 1
                if ($m) { $g = ($m.Matches[0].Groups[1].Value -replace '\*', '').Trim(); if ($g) { $V = $g } }
                [void]$sb.Append("- **$($d.BaseName)** " + [char]0x00B7 + " $V " + [char]0x00B7 + " ``morning/drafts/$Today/$($d.Name)```n")
            }
            [void]$sb.Append("`nTo grade the ungraded ones and ship any of them, run ``/morning`` with no flag.`n")
            [IO.File]::AppendAllText($PlanFile, $sb.ToString(), $script:Utf8NoBom)
            if ((Invoke-Python $NotifyArgs) -ne 0) {
                Write-RunLog "brief-update: re-delivery failed, the appended index is still in the plan file"
            }
        }
    }

    # Success toast, the pendant of the macOS notification. Only when this run delivered.
    if ($Delivered) {
        $Rt = Get-ReceiptText $ReceiptFile
        $Bid = [regex]::Match($Rt, '"brief_id":\s*(\d+)').Groups[1].Value
        Show-Alert "Morning Brief #$Bid" "Today's brief is ready ($Channel)."
    }

    # Derive the exit code from the DELIVERABLE, not from the process alone. Health checks the
    # END result.
    $PlanOk = Test-Path -LiteralPath $PlanFile
    $SentOk = Test-Delivered $ReceiptFile
    if ($null -eq $ExitCode) { $ExitCode = 0 }
    if     (-not $PlanOk) { $ExitCode = 3 }
    elseif (-not $SentOk) { $ExitCode = 4 }
    elseif ($TimedOut)    { $ExitCode = 124 }
    else                  { $ExitCode = 0 }
    Write-RunLog "RESULT: plan_file=$PlanOk delivered=$SentOk -> exit $ExitCode"

    # ON-TIME RECORD. Lag between the scheduled fire and the first delivery, written into
    # today's receipt and upserted as ONE run-log line per day, by the runner, because the
    # model's own Phase 2c line is exactly what is missing on a bad day. Before the finished
    # line, so this run's block is still open and counts. ontime.py reads launchd.log by
    # default, so it is pointed at this log explicitly.
    if ((Invoke-Python @($Ontime, '--root', $WorkDir, '--launchd-log', $script:Log, 'record', '--date', $Today)) -ne 0) {
        Write-RunLog "on-time: ontime.py record failed, receipt left as it was"
    }

    Write-RunLog "===== $(Get-Stamp) finished (exit $ExitCode) ====="
    exit $ExitCode
} finally {
    Set-KeepAwake $false
    Remove-Item -LiteralPath $LockDir -Recurse -Force -ErrorAction SilentlyContinue
}
