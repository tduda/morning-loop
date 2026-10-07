# Registers the Windows Task Scheduler entries for run-prep.ps1: the Windows pendant of
# scripts/com.morning-loop.prep.plist.template and com.morning-loop.catchup.plist.template.
#
# Copy to scripts/register-prep-task.ps1 (gitignored), fill the FILL line, run once from a normal
# PowerShell (per-user tasks, no admin needed):
#     powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\register-prep-task.ps1
#     Get-ScheduledTask -TaskName MorningLoop-*        # expect EXACTLY two: Prep and Catchup
#
# Two tasks, same split as on macOS:
#   MorningLoop-Prep     weekdays 07:52, unconditional run. WakeToRun asks Windows to wake the
#                        machine for it (only works where the power plan allows wake timers).
#   MorningLoop-Catchup  run-prep.ps1 -IfMissing, at logon and every 15 minutes from 07:45 for
#                        4h15m on weekdays. The runner exits at once, silently, unless it is a
#                        weekday between 07:45 and 12:00 and today's brief has not been
#                        delivered. On a normal day every tick is a no-op. This is what makes the
#                        brief arrive when the 07:52 fire lands on a sleeping or offline machine:
#                        the trigger becomes "the machine is really awake and a brief is owed".
# Both have StartWhenAvailable, so a start missed while the machine was off or asleep runs as
# soon as possible afterwards. The runner's lock stops the two tasks, or a hand-run, from ever
# racing; MultipleInstances IgnoreNew is the scheduler-side half of that.
#
# The older single-task setup (logon + unlock + 08:00 triggers on MorningLoop-Prep) is replaced:
# registering with -Force overwrites it. The unlock trigger is gone on purpose, the catch-up
# covers it without running the full prep on every unlock.
#
# Remove:
#     Unregister-ScheduledTask -TaskName MorningLoop-Prep    -Confirm:$false
#     Unregister-ScheduledTask -TaskName MorningLoop-Catchup -Confirm:$false
#
# More than two MorningLoop-* entries means runs racing. If you migrated from an older path or
# task name, unregister the old task before registering these.

$RunPrep     = "<FULL PATH OF YOUR run-prep.ps1>"                # FILL: absolute, no ~, e.g. C:\work\ws\morning\engine\run-prep.ps1
$PrepTask    = "MorningLoop-Prep"                                # must match $TaskName inside run-prep.ps1
$CatchupTask = "MorningLoop-Catchup"
$PrepAt      = "07:52"

if (-not (Test-Path -LiteralPath $RunPrep)) { throw "run-prep.ps1 not found at $RunPrep. Fill the path first." }

$User     = "$env:USERDOMAIN\$env:USERNAME"
$Weekdays = @('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')
$Ps       = "powershell.exe"
$BaseArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$RunPrep`""

# Interactive (logged-on user) principal, Limited run level: no admin, no stored password.
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited

# 2h execution limit is a backstop only; run-prep.ps1 has its own awake-time watchdog (50 min).
$PrepSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$CatchupSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# ---- MorningLoop-Prep: weekdays at 07:52 -------------------------------------------------------
$PrepAction  = New-ScheduledTaskAction -Execute $Ps -Argument $BaseArgs
$PrepTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekdays -At $PrepAt

Register-ScheduledTask -TaskName $PrepTask -Action $PrepAction -Trigger $PrepTrigger `
    -Settings $PrepSettings -Principal $Principal `
    -Description "Morning Loop unattended pre-run (read-only /morning --prep + delivery safety net), weekdays $PrepAt" `
    -Force | Out-Null

# ---- MorningLoop-Catchup: -IfMissing at logon, and every 15 min 07:45 to 12:00 on weekdays -------
$CatchupAction = New-ScheduledTaskAction -Execute $Ps -Argument "$BaseArgs -IfMissing"

# New-ScheduledTaskTrigger -Weekly has no repetition switches, so borrow a Repetition object from
# a -Once trigger (the documented 5.1-compatible way) and attach it: PT15M for PT4H15M from 07:45
# covers 07:45 to 12:00. The runner's own clock check is the real window; this only bounds ticks.
$Window = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Weekdays -At "07:45"
$Rep    = (New-ScheduledTaskTrigger -Once -At "07:45" `
            -RepetitionInterval (New-TimeSpan -Minutes 15) `
            -RepetitionDuration (New-TimeSpan -Hours 4 -Minutes 15)).Repetition
$Window.Repetition = $Rep

# At logon: opening the laptop and signing in is the most reliable "really awake" signal there is.
# The runner no-ops outside the weekday morning window, so a logon at 15:00 or on a Sunday is free.
$Logon = New-ScheduledTaskTrigger -AtLogOn -User $User

Register-ScheduledTask -TaskName $CatchupTask -Action $CatchupAction -Trigger @($Window, $Logon) `
    -Settings $CatchupSettings -Principal $Principal `
    -Description "Morning Loop catch-up: run-prep.ps1 -IfMissing. No-op unless a weekday brief is still owed between 07:45 and 12:00." `
    -Force | Out-Null

# ---- What was registered, and how to check it ---------------------------------------------------
Write-Host ""
Write-Host "Registered (per-user, no admin):"
foreach ($n in @($PrepTask, $CatchupTask)) {
    $t = Get-ScheduledTask -TaskName $n
    $info = Get-ScheduledTaskInfo -TaskName $n
    Write-Host ("  {0,-20} state={1,-6} next run={2}" -f $t.TaskName, $t.State, $info.NextRunTime)
    foreach ($tr in $t.Triggers) {
        $kind = $tr.CimClass.CimClassName -replace '^MSFT_Task', '' -replace 'Trigger$', ''
        $rep = ''
        if ($tr.Repetition -and $tr.Repetition.Interval) { $rep = " repeat $($tr.Repetition.Interval) for $($tr.Repetition.Duration)" }
        Write-Host ("      trigger: {0} {1}{2}" -f $kind, $tr.StartBoundary, $rep)
    }
    Write-Host ("      action:  {0} {1}" -f $t.Actions[0].Execute, $t.Actions[0].Arguments)
}
Write-Host ""
Write-Host "Verify:"
Write-Host "  Get-ScheduledTask -TaskName MorningLoop-*            # expect exactly two"
Write-Host "  Start-ScheduledTask -TaskName $CatchupTask         # outside 07:45 to 12:00 this is a silent no-op, Last Run Result 0"
Write-Host "  Get-ScheduledTaskInfo -TaskName $PrepTask | Format-List LastRunTime, LastTaskResult, NextRunTime"
Write-Host "  Get-Content <workspace>\morning\state\runner.log -Tail 20"
Write-Host ""
Write-Host "Do ONE supervised run first if you have not: powershell -NoProfile -ExecutionPolicy Bypass -File `"$RunPrep`""
