#!/bin/zsh
# Morning Loop unattended pre-run, OpenCode edition. Invoked by launchd on weekday
# mornings (com.morning-loop.prep at the fixed time, com.morning-loop.catchup with
# --if-missing every 15 minutes). Runs the read-only SENSE + PLAN half of /morning
# and writes today's plan file. Does NOT dispatch: that stays interactive (the
# morning gate).
#
# This is run-prep.template.sh (the Claude Code runner) with the client swapped.
# Everything that is not the invocation (guard, lock, network gate, caffeinate, the
# wall-clock watchdog, the delivery and brief-update safety nets, alert_on_miss,
# the on-time record) is deliberately identical, because each of those was paid for
# by a real failed run and none of them are Claude-specific. When you change one of
# them, change it in both runners.
#
# Differences from the Claude runner, all deliberate:
#   - the invocation (INVOCATION below) and the auth-failure strings it greps for
#   - an extra "runner invocation is wrong" and "opencode not found" classification
#   - the catch-up treats `rendered_not_sent` (channel file) as delivered, so a
#     file-channel adopter is not re-run every 15 minutes until noon
#
# STATUS: the OpenCode invocation has NOT yet had a live unattended run against a
# real opencode install from this template. Do one supervised run by hand before
# trusting launchd with it.
#
# Env knobs (all optional):
#   MORNING_MODEL          pin a model, e.g. github-copilot/claude-opus-5
#   MORNING_INVOKE_MODE    command (default) or message, see INVOCATION
#   MORNING_WATCHDOG_SECS  awake-time budget for the run, default 3000
#   MORNING_NET_HOST       host the network gate probes on 443, default api.anthropic.com
#                          (any always-up host proves Wi-Fi is up; set it to your
#                          provider's API host if you prefer, e.g. api.githubcopilot.com)
#   MORNING_NET_WAIT_SECS / MORNING_NET_STEP_SECS   network gate limits, 300 / 10
#   MORNING_NO_ALERT=1     skip the macOS notifications (receipts and log lines are
#                          still written). For tests and for headless boxes.

# launchd gives a minimal environment. opencode ships as a standalone binary in
# ~/.opencode/bin, which is on no system PATH, so the run dies as "command not
# found" in a log nobody opens. bun and node are here for the MCP servers, not
# for opencode itself.
#
# Deliberately NOT using the fnm shim path: fnm puts node under
# ~/.local/state/fnm_multishells/<pid>_<timestamp>/bin, which is created per
# interactive shell and will not exist when launchd runs this. Point at a stable
# install instead.
export PATH="$HOME/.opencode/bin:$HOME/.bun/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

WORKDIR="<PATH TO YOUR WORKSPACE>"   # FILL: the folder you ran setup.py on
MODEL="${MORNING_MODEL:-}"           # optional pin, e.g. github-copilot/claude-opus-5
LOG="$WORKDIR/morning/state/runner.log"
cd "$WORKDIR" || { echo "$(date) FAILED cd $WORKDIR" >> "$LOG"; exit 1; }

# Notifications go through osascript by absolute path, so a test cannot shadow it
# with a stub on PATH. MORNING_NO_ALERT=1 is the switch instead.
osa_notify() {   # osa_notify <title> <subtitle> <body>
  [ "${MORNING_NO_ALERT:-0}" = "1" ] && return 0
  [ "$(uname)" = "Darwin" ] && /usr/bin/osascript -e "display notification \"$3\" with title \"$1\" subtitle \"$2\" sound name \"Basso\"" >/dev/null 2>&1
}

# Portable timestamp formatting. date -r is BSD; date -d is GNU.
fmt_time() {   # fmt_time <unix_seconds>
  if [ "$(uname)" = "Darwin" ]; then
    date -r "$1" '+%H:%M:%S'
  else
    date -d "@$1" '+%H:%M:%S'
  fi
}

# `sent` covers macos and mattermost. `rendered_not_sent` is what channel `file`
# records: the page exists, so today's brief is done and must not be redone.
DELIVERED_RE='"status": "(sent|rendered_not_sent)"'

# ---------------------------------------------------------------------------
# GUARD + LOCK.
#
# A fixed fire time lands, on a laptop, in a DarkWake on battery: a few seconds
# awake, no keychain, no Wi-Fi. The failures that produced read as "login expired"
# and "Mac slept mid-run", and they were one cause. caffeinate cannot fix it (-s
# holds only on AC power). The fix is to stop treating "it is 07:52" as the
# trigger and start treating "the Mac is genuinely awake and a brief is still
# owed" as the trigger, which is what --if-missing does. launchd coalesces
# StartInterval across sleep, so the first real wake wins.
#
# --if-missing  = catch-up mode. Exit silently unless a brief is genuinely owed.
# (no flag)     = an unconditional run. Used by the fixed-time job and by a human
#                 running the script by hand.
# ---------------------------------------------------------------------------
IF_MISSING=0
[ "$1" = "--if-missing" ] && IF_MISSING=1

TODAY_G=$(date '+%Y-%m-%d')
RECEIPT_G="$WORKDIR/morning/state/receipts/$TODAY_G.json"
PLAN_G="$WORKDIR/morning/briefs/$TODAY_G.md"

if [ "$IF_MISSING" = "1" ]; then
  # Weekdays only. %u is 1=Mon .. 7=Sun.
  [ "$(date '+%u')" -gt 5 ] && exit 0
  # Only chase during the morning window.
  HHMM=$((10#$(date '+%H%M')))
  { [ "$HHMM" -lt 745 ] || [ "$HHMM" -gt 1200 ]; } && exit 0
  # Already delivered? This is the silent exit most ticks take, so it must be
  # cheap and must not touch the log. Checks the RECEIPT, not the plan file: a
  # plan file with a failed delivery is still an undelivered brief.
  grep -qE "$DELIVERED_RE" "$RECEIPT_G" 2>/dev/null && exit 0
fi

# One run at a time. mkdir is atomic, so this is a real mutex rather than a
# check-then-write race. It closes the scheduled-vs-manual overlap: a fixed-time
# run still going at 09:30 and a hand-invoked run writing the same plan and receipt.
LOCKDIR="$WORKDIR/morning/state/.run.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  LOCKPID=$(cat "$LOCKDIR/pid" 2>/dev/null)
  if [ -n "$LOCKPID" ] && kill -0 "$LOCKPID" 2>/dev/null; then
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') skipped: a run is already in progress (pid $LOCKPID) =====" >> "$LOG"
    exit 0
  fi
  # Stale lock from a killed run. Reclaim it.
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') reclaiming stale lock (pid ${LOCKPID:-unknown} is gone) =====" >> "$LOG"
  rm -rf "$LOCKDIR"; mkdir "$LOCKDIR" 2>/dev/null || exit 0
fi
echo $$ > "$LOCKDIR/pid"
trap 'rm -rf "$LOCKDIR"' EXIT INT TERM

# caffeinate where it exists (it always does on macOS; the guard keeps the script
# usable on a box without it). -w ties the assertion to this script's pid.
HAVE_CAFF=0
command -v caffeinate >/dev/null 2>&1 && HAVE_CAFF=1

# ---------------------------------------------------------------------------
# NETWORK GATE. Wait for the network before launching the run, bounded.
#
# A DarkWake on battery does not bring Wi-Fi with it. Without this gate the run
# burns its budget on DNS and reports a generic "prep failed (exit 1)", which names
# no cause and suggests the wrong fix. So: poll until NET_HOST resolves AND accepts
# TCP on 443, every NET_STEP_SECS, for at most NET_WAIT_SECS of WALL CLOCK (a
# DarkWake can suspend this loop too, so the deadline is read from the clock).
# If it never comes up: one log line, a failed receipt with stage "no network at
# fire time", a notification once per day for this cause, exit 75 (EX_TEMPFAIL).
# Runs BEFORE the "starting" line, so a gate miss never opens a runner block.
# ---------------------------------------------------------------------------
NET_HOST="${MORNING_NET_HOST:-api.anthropic.com}"
NET_WAIT_SECS="${MORNING_NET_WAIT_SECS:-300}"
NET_STEP_SECS="${MORNING_NET_STEP_SECS:-10}"
ONTIME="$WORKDIR/morning/engine/ontime.py"

# Portable network probe: Python socket on all platforms, fallback to nc.
# Skip with MORNING_SKIP_NET_GATE=1 (for tests).
net_up() {
  if [ "${MORNING_SKIP_NET_GATE:-0}" = "1" ]; then
    return 0
  fi
  python3 -c "import socket; socket.create_connection(('$NET_HOST', 443), 4)" >/dev/null 2>&1 && return 0
  # Fallback: nc without -G (macOS flag not on Linux). -w 4 is the timeout on both.
  nc -z -w 4 "$NET_HOST" 443 >/dev/null 2>&1
}

net_cause() {
  if python3 -c "import socket; socket.getaddrinfo('$NET_HOST', 443)" >/dev/null 2>&1; then
    echo "DNS resolves but port 443 is unreachable"
  else
    echo "DNS does not resolve $NET_HOST"
  fi
}

[ "$HAVE_CAFF" = "1" ] && { caffeinate -ims -w $$ >/dev/null 2>&1 & }   # hold the wake for the wait itself
NET_T0=$(date +%s)
NET_DEADLINE=$((NET_T0 + NET_WAIT_SECS))
while ! net_up; do
  if [ "$(date +%s)" -ge "$NET_DEADLINE" ]; then
    net_up && break                      # one last try after a thaw past the deadline
    CAUSE=$(net_cause)
    WAITED=$(( $(date +%s) - NET_T0 ))
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') no network at fire time: $CAUSE after waiting ${WAITED}s (limit ${NET_WAIT_SECS}s). Not starting the run; the catch-up retries on its next tick. =====" >> "$LOG"
    mkdir -p "$(dirname "$RECEIPT_G")"
    if ! grep -qE "$DELIVERED_RE" "$RECEIPT_G" 2>/dev/null; then
      PRIOR_STAGE=$(grep -o '"stage": "[^"]*"' "$RECEIPT_G" 2>/dev/null)
      if [ "$(uname)" = "Darwin" ]; then
        NET_ERR="$CAUSE after waiting ${WAITED}s. This is often a DarkWake on battery, which brings no Wi-Fi. The catch-up retries every 15 minutes; mains power overnight fixes it."
      else
        NET_ERR="$CAUSE after waiting ${WAITED}s. The catch-up retries every 15 minutes."
      fi
      printf '{\n  "date": "%s",\n  "status": "failed",\n  "stage": "no network at fire time",\n  "error": "%s",\n  "checked_at": "%s"\n}\n' \
        "$TODAY_G" "$NET_ERR" "$(date '+%Y-%m-%dT%H:%M:%S%z')" > "$RECEIPT_G"
      if [ "$PRIOR_STAGE" != '"stage": "no network at fire time"' ]; then
        osa_notify "⚠️ Morning brief waiting for network" "No network at fire time" "$CAUSE. The catch-up will retry once there is a network."
      fi
    fi
    python3 "$ONTIME" record --date "$TODAY_G" >> "$LOG" 2>&1
    exit 75
  fi
  sleep "$NET_STEP_SECS"
done
NET_WAITED=$(( $(date +%s) - NET_T0 ))
[ "$NET_WAITED" -gt 0 ] && echo "===== $(date '+%Y-%m-%d %H:%M:%S') network up after ${NET_WAITED}s =====" >> "$LOG"

MODE_NOTE=""
[ "$IF_MISSING" = "1" ] && MODE_NOTE=" (catch-up: no delivered brief for $TODAY_G yet)"
echo "===== $(date '+%Y-%m-%d %H:%M:%S') starting /morning --prep (opencode)$MODE_NOTE =====" >> "$LOG"

# Record where this run's slice of the cumulative log starts, so the failure
# classifier reads only THIS run and not weeks of history.
LOG_START=$(wc -c < "$LOG" 2>/dev/null || echo 0)

# INVOCATION. `opencode run` is the headless, single-shot form. Two shapes work
# depending on version; MODE picks one so the first supervised run can flip it in
# one line instead of editing the command:
#   command  ->  opencode run --command morning -- --prep     (explicit command)
#   message  ->  opencode run "/morning --prep"               (slash in the prompt)
# The --prep path is read-only beyond local file writes; it never performs a
# never_auto external action (those are interactive-only by design).
#
# Note: --allowedTools is Claude Code only. OpenCode and Codex may need separate
# permission configuration; see your client's docs for how to pre-approve MCP connectors.
MODE="${MORNING_INVOKE_MODE:-command}"
set -- run
[ -n "$MODEL" ] && set -- "$@" --model "$MODEL"
if [ "$MODE" = "command" ]; then
  set -- "$@" --command morning -- --prep
else
  set -- "$@" "/morning --prep"
fi

# caffeinate -ims for the life of the run. -i alone was not enough: a DarkWake
# returning to maintenance sleep is not idle sleep, so -m and -s as well. HONEST
# LIMIT: -s holds only on AC power; on battery with the lid shut nothing keeps the
# machine up. The belt-and-braces half is a scheduled wake, a machine-level power
# setting deliberately NOT done from this script:
#   sudo pmset repeat wakeorpoweron MTWRF 07:50:00
if [ "$HAVE_CAFF" = "1" ]; then
  caffeinate -ims opencode "$@" >> "$LOG" 2>&1 &
else
  opencode "$@" >> "$LOG" 2>&1 &
fi
RUN_PID=$!

# WALL-CLOCK-AWARE WATCHDOG. A plain `sleep N` suspends with the machine, so a run
# that froze in a DarkWake and thawed at lid-open froze and thawed together with
# its own watchdog (one run went 07:52 to 17:38 against a "50 minute" limit). This
# one ticks every WD_TICK seconds and reads the clock: a tick that took far longer
# than WD_TICK means the machine slept, which is logged as `watchdog: machine slept
# for about N min` and NOT counted against the budget. The budget is AWAKE time.
# The classifier below reads that line, so a frozen run reports `slept`, never
# `timeout`, and ontime.py carries the slept minutes into the receipt.
# The explicit redirect matters: without it the watchdog holds the caller's pipe.
WD_BUDGET="${MORNING_WATCHDOG_SECS:-3000}"
WD_TICK=15
( awake=0; last=$(date +%s)
  while kill -0 "$RUN_PID" 2>/dev/null; do
    sleep "$WD_TICK"
    now=$(date +%s); gap=$((now - last))
    if [ "$gap" -gt $((WD_TICK * 4 + 60)) ]; then
      echo "watchdog: machine slept for about $((gap / 60)) min (wall clock $(fmt_time "$last") to $(fmt_time "$now")), not counted against the budget"
    else
      awake=$((awake + gap))
    fi
    last=$now
    if [ "$awake" -ge "$WD_BUDGET" ] && kill -0 "$RUN_PID" 2>/dev/null; then
      echo "watchdog: prep exceeded $((WD_BUDGET / 60)) min awake, killing $RUN_PID"
      kill -TERM "$RUN_PID" 2>/dev/null
      break
    fi
  done ) >> "$LOG" 2>&1 &
WATCHDOG_PID=$!
wait "$RUN_PID"

STATUS=$?
# Reap the sleep BEFORE its parent: killing the subshell alone orphans the sleep,
# which keeps an inherited stdout open and makes anything waiting on this script
# block until the tick ends.
pkill -P "$WATCHDOG_PID" 2>/dev/null
kill "$WATCHDOG_PID" 2>/dev/null      # run finished in time; retire the watchdog
echo "===== $(date '+%Y-%m-%d %H:%M:%S') opencode finished (exit $STATUS) =====" >> "$LOG"

# --------------------------------------------------------------------------
# DELIVERY SAFETY NET. Phase 2b is supposed to deliver the brief itself. This
# block does not trust that: if no delivered receipt exists for today, it
# delivers here. Idempotent: the notifier reuses today's brief id.
# --------------------------------------------------------------------------
# The day the run STARTED, not the day it ended: a run that thaws after midnight
# must not write its receipt to the next day.
TODAY="$TODAY_G"
PLAN="$WORKDIR/morning/briefs/$TODAY.md"
RECEIPT="$WORKDIR/morning/state/receipts/$TODAY.json"
NOTIFIER="$WORKDIR/morning/engine/notify.py"

# Optional overrides (channel, webhook). Absent by default.
[ -f "$HOME/.config/morning-loop/notify.env" ] && . "$HOME/.config/morning-loop/notify.env"

# alert_on_miss. A failure that only reaches a log file IS a silent failure. So
# every failure path notifies, using osascript directly rather than the notifier
# script, because it must still work when the run itself is broken. Also writes a
# `failed` receipt, so tomorrow's HEALTH check can tell "failed for this reason"
# from "never attempted".
alert_on_miss() {
  reason="$1"; detail="$2"
  echo "alert: $reason - $detail" >> "$LOG"
  osa_notify "⚠️ Morning brief did NOT run" "$reason" "$detail"
  mkdir -p "$WORKDIR/morning/state/receipts"
  printf '{\n  "date": "%s",\n  "status": "failed",\n  "stage": "%s",\n  "error": "%s",\n  "checked_at": "%s"\n}\n' \
    "$TODAY" "$reason" "$detail" "$(date '+%Y-%m-%dT%H:%M:%S%z')" \
    > "$RECEIPT"
}

RUN_LOG=$(tail -c "+$((LOG_START + 1))" "$LOG" 2>/dev/null)

# alert_partial. A watchdog kill mid-pre-draft is NOT a missing brief: the brief
# went out, so the block below says nothing. This notifies WITHOUT overwriting the
# good receipt, and leaves a sidecar so tomorrow's HEALTH check can see it.
alert_partial() {
  reason="$1"; detail="$2"
  echo "alert(partial): $reason - $detail" >> "$LOG"
  osa_notify "⚠️ Brief delivered, drafting cut short" "$reason" "$detail"
  printf '{\n  "date": "%s",\n  "status": "partial",\n  "stage": "%s",\n  "detail": "%s",\n  "checked_at": "%s"\n}\n' \
    "$TODAY" "$reason" "$detail" "$(date '+%Y-%m-%dT%H:%M:%S%z')" \
    > "$WORKDIR/morning/state/receipts/$TODAY.partial.json"
}

SLEPT_MIN=$(printf '%s' "$RUN_LOG" | sed -n 's/^watchdog: machine slept for about \([0-9]*\) min.*/\1/p' | awk '{s+=$1} END {print s+0}')
if printf '%s' "$RUN_LOG" | grep -q "watchdog: prep exceeded"; then
  DRAFT_DIR="$WORKDIR/morning/drafts/$TODAY"
  N_DRAFTS=$(ls -1 "$DRAFT_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')
  N_VERIFIED=$(grep -l "VERIFY RESULTS" "$DRAFT_DIR"/*.md 2>/dev/null | wc -l | tr -d ' ')
  if [ "$SLEPT_MIN" -gt 0 ]; then
    alert_partial "The Mac slept mid-run (${SLEPT_MIN} min), then the watchdog stopped it" "$N_DRAFTS drafts written, $N_VERIFIED verified. The brief still says drafting. Run /morning to finish and grade them."
  else
    alert_partial "Watchdog killed the run" "$N_DRAFTS drafts written, $N_VERIFIED verified. The brief still says drafting. Run /morning to finish and grade them."
  fi
  # A watchdog-killed run is otherwise invisible in the run-log evidence trail:
  # Phase 2c never runs, so nothing writes its line. Log it from the runner.
  printf '\n- %s run: **watchdog-killed after %s min of awake time**, auto-logged by run-prep (opencode) because Phase 2c never ran. Pre-drafted **%s** file(s) in `morning/drafts/%s/`, **%s** carrying a verify stamp. Brief delivery: see `delivery-receipts/%s.json`. This line exists so the run is not invisible in the evidence trail; the qualitative detail is absent because the run was killed before it could write it.\n' \
    "$TODAY" "$((WD_BUDGET / 60))" "$N_DRAFTS" "$TODAY" "$N_VERIFIED" "$TODAY" \
    >> "$WORKDIR/morning/state/run-log.md"
fi

if grep -qE "$DELIVERED_RE" "$RECEIPT" 2>/dev/null; then
  echo "delivery: already delivered today, nothing to do" >> "$LOG"
elif [ ! -f "$PLAN" ]; then
  # Diagnose WHY from what opencode actually said, because "it didn't run" is
  # useless and "your auth expired" is actionable. Read ONLY this run's slice:
  # grepping the cumulative log once misreported every later exit-1 as a login
  # expiry, forever, after the string appeared a single time.
  if [ "$SLEPT_MIN" -gt 0 ] || printf '%s' "$RUN_LOG" | grep -qi "went to sleep\|Connection closed mid-response"; then
    if [ "$(uname)" = "Darwin" ]; then
      alert_on_miss "The Mac slept mid-run" "launchd woke it, macOS put it back to sleep before the run finished. Check caffeinate is in run-prep, then run /morning."
    else
      alert_on_miss "The system slept mid-run" "The run started but was interrupted by sleep before it finished. Check the scheduler config, then run /morning."
    fi
  elif printf '%s' "$RUN_LOG" | grep -qi "command not found: opencode\|opencode: command not found\|opencode: not found\|no such file or directory: opencode"; then
    alert_on_miss "OpenCode not found" "The opencode binary is not on the runner's PATH. Fix the export PATH line in run-prep, then run /morning."
  elif printf '%s' "$RUN_LOG" | grep -qi "not authenticated\|auth.*expired\|invalid api key\|please run.*auth\|please run.*login\|unauthorized\|Failed to authenticate\|OAuth session expired\|no credentials"; then
    alert_on_miss "OpenCode auth expired" "Run: opencode auth login in the terminal, then /morning to get today's brief."
  elif printf '%s' "$RUN_LOG" | grep -qi "unknown command\|invalid choice\|unknown option\|unknown argument"; then
    alert_on_miss "Runner invocation is wrong" "opencode rejected the command. Flip MORNING_INVOKE_MODE (command|message) in run-prep and retest."
  elif printf '%s' "$RUN_LOG" | grep -qi "ENOTFOUND\|EAI_AGAIN\|Can't reach the API server\|getaddrinfo\|Could not resolve host\|Network is unreachable\|Unable to connect"; then
    alert_on_miss "Lost the network mid-run" "The run started with a network and then lost it, so the API became unreachable. The catch-up will retry once it has a network."
  elif printf '%s' "$RUN_LOG" | grep -qi "mcp.*timeout\|mcp.*timed out\|sse.*closed\|sse.*disconnected\|sse.*timeout\|event stream.*closed\|event stream.*ended\|econnreset\|connection reset by peer"; then
    alert_on_miss "An MCP server dropped mid-run (SSE/stream timeout)" "A tool server's stream died, so the run could not finish. Re-run /morning manually; if it recurs, reconnect that MCP server."
  elif [ $STATUS -ne 0 ]; then
    if [ "$(uname)" = "Darwin" ]; then
      alert_on_miss "The prep run failed (exit $STATUS)" "No brief today. Check launchd.log, then run /morning manually."
    else
      alert_on_miss "The prep run failed (exit $STATUS)" "No brief today. Check the runner log, then run /morning manually."
    fi
  else
    if [ "$(uname)" = "Darwin" ]; then
      alert_on_miss "No plan file was written" "The run finished but produced nothing. Check launchd.log."
    else
      alert_on_miss "No plan file was written" "The run finished but produced nothing. Check the runner log."
    fi
  fi
  STATUS=1
else
  echo "delivery: no delivered receipt for $TODAY, delivering from the safety net" >> "$LOG"
  python3 "$NOTIFIER" --brief "$PLAN" --date "$TODAY" >> "$LOG" 2>&1
  SEND_STATUS=$?
  if [ $SEND_STATUS -ne 0 ]; then
    alert_on_miss "Brief written but delivery failed" "The plan exists but did not reach you. See $RECEIPT"
    STATUS=$SEND_STATUS
  fi
fi

# --------------------------------------------------------------------------
# BRIEF-UPDATE SAFETY NET. Phase 2p is supposed to update the brief in place as
# each draft lands and re-run the notifier. When the watchdog fires mid-drafting
# it never gets there, and the brief still lists finished drafts as pending to-dos.
# So: if drafts exist for today and the plan file is OLDER than the newest draft,
# append a factual index of what was produced and re-deliver (same date, same id).
# A deterministic file listing, not a summary: the runner cannot read the drafts
# and a fabricated summary would be worse than none.
# --------------------------------------------------------------------------
DRAFT_DIR="$WORKDIR/morning/drafts/$TODAY"
if [ -d "$DRAFT_DIR" ] && [ -n "$(ls -A "$DRAFT_DIR"/*.md 2>/dev/null)" ] && [ -f "$PLAN" ]; then
  NEWEST_DRAFT=$(ls -t "$DRAFT_DIR"/*.md 2>/dev/null | head -1)
  if [ -n "$NEWEST_DRAFT" ] && [ "$NEWEST_DRAFT" -nt "$PLAN" ]; then
    echo "brief-update: drafts are newer than the brief, appending the index and re-delivering" >> "$LOG"
    {
      printf '\n\n---\n\n## 🤖 DRAFTS PRODUCED THIS RUN (appended by run-prep at %s)\n\n' "$(date '+%H:%M')"
      printf 'The run was cut short before it could update this section itself, so the list below was\n'
      printf 'written by the runner from the files on disk. Nothing here is sent; each ships only with\n'
      printf 'your yes. Grades come from each file'"'"'s own verify stamp, and "not graded" means exactly\n'
      printf 'that: the draft exists but no independent verifier reached it.\n\n'
      for f in "$DRAFT_DIR"/*.md; do
        [ -f "$f" ] || continue
        V=$(grep -m1 -o 'Verdict: *[A-Za-z ]*' "$f" 2>/dev/null | sed 's/Verdict: *//' | tr -d '*')
        [ -z "$V" ] && V="not graded"
        printf -- '- **%s** · %s · `%s`\n' "$(basename "$f" .md)" "$V" "morning/drafts/$TODAY/$(basename "$f")"
      done
      printf '\nTo grade the ungraded ones and ship any of them, run `/morning` with no flag.\n'
    } >> "$PLAN"
    python3 "$NOTIFIER" --brief "$PLAN" --date "$TODAY" >> "$LOG" 2>&1 \
      || echo "brief-update: re-delivery failed, the appended index is still in the plan file" >> "$LOG"
  fi
fi

# ON-TIME RECORD. Lag between the scheduled fire and the first delivery, written
# into today's receipt and upserted as ONE run-log line per day, by the runner,
# because the model's own Phase 2c line is exactly what is missing on a bad day.
# Runs before the finished line, so this run's block is still open and counts.
python3 "$ONTIME" record --date "$TODAY" >> "$LOG" 2>&1 \
  || echo "on-time: ontime.py record failed, receipt left as it was" >> "$LOG"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') finished (exit $STATUS) =====" >> "$LOG"
exit $STATUS
