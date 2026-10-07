#!/bin/zsh
# Morning Loop unattended pre-run. Invoked by launchd on weekday mornings.
# Runs the read-only SENSE + PLAN half of /morning and writes today's plan file.
# Does NOT dispatch — that stays interactive (the morning gate).

# launchd gives a minimal environment; set PATH explicitly for claude + node + jq + python.
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

WORKDIR="<PATH TO YOUR WORKSPACE>"   # FILL: the folder you ran setup.py on

# FILL (optional): connector tools the unattended run may call without asking. None by
# default; with none listed the run still finishes, with a thinner brief, because in
# --print mode a connector call that isn't approved is denied, not prompted. List
# READ-ONLY tools by full name, mcp__<server>__<tool>, where <server> is the name you
# gave the connector in Claude Code. Never "mcp__<server>" or "mcp__<server>__*": those
# approve that server's write tools too (create an issue, post, send mail), in a run
# that reads inbox and chat, which anyone can write into.
MORNING_ALLOWED_TOOLS=(
  # "mcp__atlassian__getJiraIssue"               # examples only: tool names
  # "mcp__atlassian__searchJiraIssuesUsingJql"   # differ by server, check yours
)
LOG="$WORKDIR/morning/state/runner.log"
cd "$WORKDIR" || { echo "$(date) FAILED cd $WORKDIR" >> "$LOG"; exit 1; }

# ---------------------------------------------------------------------------
# GUARD + LOCK. Added 2026-08-25 after diagnosing why the loop kept not firing.
#
# THE ROOT CAUSE, and it is one cause rather than the two we thought:
# a fixed 07:52 StartCalendarInterval fires while the Mac is asleep on battery,
# in a DarkWake / maintenance-sleep cycle. Measured on 2026-08-25:
#   07:51:49 DarkWake -> 07:51:51 Sleep   (2 seconds, the 07:52 event never landed)
#   08:09:43 launchd fires the coalesced job
#   08:09:44 DarkWake -> 08:09:47 Sleep   -> 08:09:48 claude exit 1
# claude got about 4 seconds. 28 power-log lines that morning read "Using BATT"
# and zero read "Using AC". In DarkWake the login keychain is not available, so
# Claude Code cannot refresh its OAuth token and reports "OAuth session expired
# and could not be refreshed". That is why the failures LOOKED like two separate
# problems ("login expired" x5, "Mac slept mid-run" x2): it is the same problem,
# reporting differently depending on how far the run got before macOS pulled out.
#
# caffeinate cannot fix this. -s holds only on AC power and the machine is on
# battery. The real fix is to stop treating "it is 07:52" as the trigger and
# start treating "the Mac is genuinely awake" as the trigger, which is what the
# --if-missing catch-up below does: it retries on a short interval through the
# morning and no-ops the moment today's brief has actually been delivered.
# launchd coalesces StartInterval across sleep, so the first real wake wins.
#
# --if-missing  = catch-up mode. Exit silently unless a brief is genuinely owed.
# (no flag)     = the old behaviour, an unconditional run. Used by the 07:52 job
#                 and by a human running the script by hand.
# ---------------------------------------------------------------------------
IF_MISSING=0
[ "$1" = "--if-missing" ] && IF_MISSING=1

TODAY_G=$(date '+%Y-%m-%d')
RECEIPT_G="$WORKDIR/morning/state/receipts/$TODAY_G.json"
PLAN_G="$WORKDIR/morning/briefs/$TODAY_G.md"

if [ "$IF_MISSING" = "1" ]; then
  # Weekdays only. %u is 1=Mon .. 7=Sun.
  [ "$(date '+%u')" -gt 5 ] && exit 0
  # Only chase during the morning window. Outside it, a missing brief is not news
  # and nobody wants the loop starting itself at 23:00.
  HHMM=$((10#$(date '+%H%M')))
  { [ "$HHMM" -lt 745 ] || [ "$HHMM" -gt 1200 ]; } && exit 0
  # Already delivered for real? Then there is nothing owed. This is the silent
  # exit that most ticks take, so it must be cheap and must not touch the log.
  # Checks the RECEIPT, not the plan file: a plan file with a failed delivery is
  # still an undelivered brief, which is the whole point of the health contract.
  # `rendered_not_sent` is the file channel's delivery: without it the catch-up
  # re-ran the whole brief every 15 minutes until noon for file-channel users.
  grep -qE '"status": "(sent|rendered_not_sent)"' "$RECEIPT_G" 2>/dev/null && exit 0
fi

# caffeinate where it exists (it always does on macOS; the guard keeps the script
# usable on a box without it).
HAVE_CAFF=0
command -v caffeinate >/dev/null 2>&1 && HAVE_CAFF=1

# Portable notifications: osascript on macOS, silent elsewhere.
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

# One run at a time. mkdir is atomic, so this is a real mutex rather than a
# check-then-write race. This closes the scheduled-vs-manual overlap an early adopter found:
# before this, a 07:52 run still going at 09:30 and a hand-invoked /morning could
# both write the same plan file and the same receipt.
LOCKDIR="$WORKDIR/morning/state/.run.lock"
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  LOCKPID=$(cat "$LOCKDIR/pid" 2>/dev/null)
  if [ -n "$LOCKPID" ] && kill -0 "$LOCKPID" 2>/dev/null; then
    echo "===== $(date '+%Y-%m-%d %H:%M:%S') skipped: a run is already in progress (pid $LOCKPID) =====" >> "$LOG"
    exit 0
  fi
  # Stale lock from a killed run (the watchdog leaves one). Reclaim it.
  echo "===== $(date '+%Y-%m-%d %H:%M:%S') reclaiming stale lock (pid ${LOCKPID:-unknown} is gone) =====" >> "$LOG"
  rm -rf "$LOCKDIR"; mkdir "$LOCKDIR" 2>/dev/null || exit 0
fi
echo $$ > "$LOCKDIR/pid"
trap 'rm -rf "$LOCKDIR"' EXIT INT TERM

# ---------------------------------------------------------------------------
# NETWORK GATE. Wait for the network before launching the run, bounded.
#
# 2026-09-28: the 07:50 run and the 09:15 catch-up both died with "API Error:
# Can't reach the API server (ENOTFOUND)". The wake fired on time, but it was a
# DarkWake on battery, and a DarkWake on battery does not bring Wi-Fi with it.
# The first run burned 37 minutes on DNS and then reported a generic "prep
# failed (exit 1)", which names no cause and suggests the wrong fix.
#
# So: poll until api.anthropic.com resolves AND accepts a TCP connection on 443,
# every NET_STEP_SECS, for at most NET_WAIT_SECS of WALL CLOCK (a DarkWake can
# suspend this loop too, so the deadline is read from the clock, not counted).
# nc does the real getaddrinfo + connect, the same path the API client takes;
# dscacheutil is asked afterwards only to NAME the cause (no DNS vs no route).
# If the network never comes up: one clear log line, a failed receipt whose
# stage is "no network at fire time", a notification once per day for this
# cause (a catch-up tick every 15 minutes must not ring every 15 minutes), and
# exit 75 (EX_TEMPFAIL). The catch-up agent retries on its next tick. This runs
# BEFORE the "starting" line, so a gate miss never opens a runner block.
# All of it is plain POSIX sh, so it is the same under zsh and bash 3.2.
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
    if ! grep -qE '"status": "(sent|rendered_not_sent)"' "$RECEIPT_G" 2>/dev/null; then
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
echo "===== $(date '+%Y-%m-%d %H:%M:%S') starting /morning --prep$MODE_NOTE =====" >> "$LOG"

# --print: headless, single-shot. --permission-mode acceptEdits lets it write the
# plan file without a prompt. The --prep path is read-only beyond local file writes;
# it never performs a never_auto external action (those are interactive-only by design).
#
# --allowedTools: one Bash rule per engine script /morning calls, written with the
# interpreter setup.py found (owner.python in config.yml), so engine calls don't stall
# on a permission prompt on a fresh account. No MCP wildcard: Claude Code ignores a
# bare "mcp__*", and "mcp__<server>" would pre-approve that server's write tools too,
# in a run that reads text anyone can write into. Connector reads are pre-approved
# only if you list them in MORNING_ALLOWED_TOOLS at the top.
#
# Bounded with a watchdog rather than `timeout`, which macOS does not ship. An
# unbounded headless invocation once burned 43 minutes failing to authenticate
# before giving up, which is time the machine might not stay awake for.
#
# The budget went 20min -> 50min on 2026-08-19, when the prep started PRE-DRAFTING
# the SOLVE items (dispatch.predraft_in_prep) instead of only planning them.
# Drafting + independent verification of up to dispatch.max_predrafts jobs is a
# much longer run than sense-and-plan. This is safe because /morning writes the
# plan and the verified findings BEFORE it starts drafting, so a watchdog kill
# still leaves a deliverable brief, and the safety net below still delivers it.
# Record where today's slice of the cumulative log starts, so the failure
# classifier below reads only THIS run and not four weeks of history.
LOG_START=$(wc -c < "$LOG" 2>/dev/null || echo 0)

PY_CFG=$(sed -n 's/^  python:[[:space:]]*\([^#]*\).*/\1/p' "$WORKDIR/morning/config.yml" 2>/dev/null | head -1 | sed 's/[[:space:]]*$//')
[ -n "$PY_CFG" ] || PY_CFG=python3
ALLOWED=()
for s in asks coach doctor notify onboard ontime reconcile_ledger sharpen shipped tickets trust; do
  ALLOWED+=("Bash($PY_CFG morning/engine/$s.py *)")
done
ALLOWED+=("${MORNING_ALLOWED_TOOLS[@]}")
echo "permissions: $(( ${#ALLOWED[@]} - ${#MORNING_ALLOWED_TOOLS[@]} )) engine rules for '$PY_CFG'; ${#MORNING_ALLOWED_TOOLS[@]} connector tool(s) pre-approved${MORNING_ALLOWED_TOOLS[*]:+: ${MORNING_ALLOWED_TOOLS[*]}}" >> "$LOG"


# (The single-shot "no network yet" check that stood here moved up into the
# NETWORK GATE above, which waits a bounded time and names the cause.)

# caffeinate holds sleep off for the life of the run. Without it a launchd DarkWake
# gives roughly 45 seconds before macOS goes back to 'Maintenance Sleep' and kills
# the in-flight API call. That is what happened on 2026-08-20: DarkWake 08:01:04,
# run started, sleep again 08:01:49, failure only surfaced at 08:12 on lid-open.
#
# -i ALONE WAS NOT ENOUGH, and 2026-08-24 proved it: -i was added after the 08-20
# miss and the run died the same way at 08:32:47 on "computer went to sleep
# mid-response". -i asserts against *idle* sleep only, and a DarkWake returning to
# maintenance sleep is not idle sleep. So: -m (no disk sleep) and -s (no system
# sleep) as well.
#
# HONEST LIMIT, do not mistake this for a guarantee: -s holds only while on AC
# power. On battery with the lid shut, no caffeinate flag will keep the machine up.
# The belt-and-braces half is a scheduled wake, which is a machine-level power
# setting and deliberately NOT done from this script:
#   sudo pmset repeat wakeorpoweron MTWRF 07:50:00
if [ "$HAVE_CAFF" = "1" ]; then
  caffeinate -ims claude --print "/morning --prep" \
    --permission-mode acceptEdits \
    --allowedTools "${ALLOWED[@]}" \
    >> "$LOG" 2>&1 &
else
  claude --print "/morning --prep" \
    --permission-mode acceptEdits \
    --allowedTools "${ALLOWED[@]}" \
    >> "$LOG" 2>&1 &
fi
CLAUDE_PID=$!
# WALL-CLOCK-AWARE WATCHDOG. `sleep 3000` suspends with the
# machine, so a run that froze in a DarkWake and thawed at lid-open froze and
# thawed together with its own watchdog (09-17 ran 07:52 to 17:38 against a
# "50 minute" limit). This one ticks every WD_TICK seconds and reads the clock:
# a tick that took far longer than WD_TICK means the machine slept, which is
# logged as `watchdog: machine slept for about N min` and NOT counted against
# the budget. The budget is 50 minutes of AWAKE time. The failure classifier
# below reads that line, so a run that froze with the machine reports `slept`,
# never `timeout`, and ontime.py carries the slept minutes into the receipt.
WD_BUDGET="${MORNING_WATCHDOG_SECS:-3000}"
WD_TICK=15
( awake=0; last=$(date +%s)
  while kill -0 "$CLAUDE_PID" 2>/dev/null; do
    sleep "$WD_TICK"
    now=$(date +%s); gap=$((now - last))
    if [ "$gap" -gt $((WD_TICK * 4 + 60)) ]; then
      echo "watchdog: machine slept for about $((gap / 60)) min (wall clock $(fmt_time "$last") to $(fmt_time "$now")), not counted against the budget"
    else
      awake=$((awake + gap))
    fi
    last=$now
    if [ "$awake" -ge "$WD_BUDGET" ] && kill -0 "$CLAUDE_PID" 2>/dev/null; then
      echo "watchdog: prep exceeded $((WD_BUDGET / 60)) min awake, killing $CLAUDE_PID"
      kill -TERM "$CLAUDE_PID" 2>/dev/null
      break
    fi
  done ) >> "$LOG" 2>&1 &
WATCHDOG_PID=$!
wait "$CLAUDE_PID"

STATUS=$?
pkill -P "$WATCHDOG_PID" 2>/dev/null  # reap its sleep first, or the orphan holds the log open
kill "$WATCHDOG_PID" 2>/dev/null      # run finished in time; retire the watchdog
echo "===== $(date '+%Y-%m-%d %H:%M:%S') claude finished (exit $STATUS) =====" >> "$LOG"

# --------------------------------------------------------------------------
# DELIVERY SAFETY NET.
# Phase 2b is supposed to deliver the brief itself. This block does not trust
# that: if no "sent" receipt exists for today, it delivers here. Delivery is the
# whole point of the loop, so it must not depend on the model remembering to
# call a script. Idempotent - the notifier reuses today's brief id.
#
# Default channel is `macos`: a native notification plus the brief rendered as a
# local web page. Zero setup, nothing to sign up for. Set MORNING_NOTIFY_CHANNEL
# to `mattermost` (with MORNING_MATTERMOST_WEBHOOK) to post it instead.
# --------------------------------------------------------------------------
# The day the run STARTED, not the day it ended. A run that began 2026-09-04 and
# thawed on 2026-09-05 at 21:54 wrote its failed receipt to a Saturday and left
# the real weekday with no receipt at all.
TODAY="$TODAY_G"
PLAN="$WORKDIR/morning/briefs/$TODAY.md"
RECEIPT="$WORKDIR/morning/state/receipts/$TODAY.json"
NOTIFIER="$WORKDIR/morning/engine/notify.py"

# Optional overrides (channel, webhook). Absent by default.
[ -f "$HOME/.config/morning-loop/notify.env" ] && . "$HOME/.config/morning-loop/notify.env"

# --------------------------------------------------------------------------
# alert_on_miss. A failure that only reaches a log file IS a silent failure:
# nobody reads a log they have no reason to open. So every failure path below
# notifies, using osascript directly rather than the notifier script, because
# the whole point is that it still works when the run itself is broken.
# Also writes a `failed` receipt, so tomorrow's HEALTH check can tell
# "failed for this reason" from "never attempted".
# --------------------------------------------------------------------------
alert_on_miss() {
  reason="$1"; detail="$2"
  echo "alert: $reason - $detail" >> "$LOG"
  osa_notify "⚠️ Morning brief did NOT run" "$reason" "$detail"
  mkdir -p "$WORKDIR/morning/state/receipts"
  printf '{\n  "date": "%s",\n  "status": "failed",\n  "stage": "%s",\n  "error": "%s",\n  "checked_at": "%s"\n}\n' \
    "$TODAY" "$reason" "$detail" "$(date '+%Y-%m-%dT%H:%M:%S%z')" \
    > "$WORKDIR/morning/state/receipts/$TODAY.json"
}

# This run's slice of the cumulative log. Hoisted out of the diagnosis branch
# below because a TRUNCATED run needs it too, not just a missing one.
RUN_LOG=$(tail -c "+$((LOG_START + 1))" "$LOG" 2>/dev/null)

# --------------------------------------------------------------------------
# alert_partial. A watchdog kill mid-pre-draft is NOT a missing brief: the brief
# went out and the receipt says "sent", so the block below reports "already
# delivered" and says nothing at all. One early run lost a planned draft
# exactly that way and nobody was told. This notifies WITHOUT overwriting the
# good receipt, and leaves a sidecar so tomorrow's HEALTH check can see it.
# --------------------------------------------------------------------------
alert_partial() {
  reason="$1"; detail="$2"
  echo "alert(partial): $reason - $detail" >> "$LOG"
  osa_notify "⚠️ Brief delivered, drafting cut short" "$reason" "$detail"
  printf '{\n  "date": "%s",\n  "status": "partial",\n  "stage": "%s",\n  "detail": "%s",\n  "checked_at": "%s"\n}\n' \
    "$TODAY" "$reason" "$detail" "$(date '+%Y-%m-%dT%H:%M:%S%z')" \
    > "$WORKDIR/morning/state/receipts/$TODAY.partial.json"
}

# Did the watchdog cut the run off? Report it whether or not the brief landed.
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

  # A watchdog-killed run is otherwise INVISIBLE in the run log. The
  # brief can land and Phase 2c never runs, so nothing writes the run-log line, and
  # the loop undercounts a run that did deliver. 2026-08-21 was lost exactly this
  # way and was only noticed on 2026-08-24 by counting run-log dates against the
  # delivery receipts. So log it here, from the runner, which is the only thing
  # still alive at this point.
  printf '\n- %s run: **watchdog-killed after 50 min of awake time**, auto-logged by run-prep.sh because Phase 2c never ran. Pre-drafted **%s** file(s) in `morning/drafts/%s/`, **%s** carrying a verify stamp. Brief delivery: see `delivery-receipts/%s.json`. This line exists so the run is not invisible in the run log; the qualitative detail is absent because the run was killed before it could write it.\n' \
    "$TODAY" "$N_DRAFTS" "$TODAY" "$N_VERIFIED" "$TODAY" \
    >> "$WORKDIR/morning/state/run-log.md"
fi

if grep -qE '"status": "(sent|rendered_not_sent)"' "$RECEIPT" 2>/dev/null; then
  echo "delivery: already delivered today, nothing to do" >> "$LOG"
elif [ ! -f "$PLAN" ]; then
  # The run never produced a brief. Diagnose WHY from what claude actually said,
  # because "it didn't run" is useless and "your login expired" is actionable.
  # Read ONLY this run's slice. Grepping the whole cumulative log meant that once
  # "Please run /login" appeared once (2026-07-27), EVERY later exit-1 was reported
  # as a login expiry forever. Four misses were misattributed that way before the
  # 2026-08-20 run, whose real cause was machine sleep, made it obvious.
  if [ "$SLEPT_MIN" -gt 0 ] || printf '%s' "$RUN_LOG" | grep -qi "went to sleep\|Connection closed mid-response"; then
    if [ "$(uname)" = "Darwin" ]; then
      alert_on_miss "The Mac slept mid-run" "launchd woke it, macOS put it back to sleep before the run finished. Check caffeinate is in run-prep.sh, then run /morning."
    else
      alert_on_miss "The system slept mid-run" "The run started but was interrupted by sleep before it finished. Check the scheduler config, then run /morning."
    fi
  elif printf '%s' "$RUN_LOG" | grep -qi "Failed to authenticate\|OAuth session expired\|Invalid API key\|Please run.*login"; then
    alert_on_miss "Claude login expired" "Run: claude /login in the terminal, then /morning to get today's brief."
  elif printf '%s' "$RUN_LOG" | grep -qi "ENOTFOUND\|EAI_AGAIN\|Can't reach the API server\|getaddrinfo\|Could not resolve host\|Network is unreachable"; then
    # Since the NETWORK GATE, a run only starts with a network, so reaching this
    # branch means the network went away DURING the run.
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
  echo "delivery: no 'sent' receipt for $TODAY, delivering from the safety net" >> "$LOG"
  python3 "$NOTIFIER" --brief "$PLAN" --date "$TODAY" >> "$LOG" 2>&1
  SEND_STATUS=$?
  if [ $SEND_STATUS -ne 0 ]; then
    alert_on_miss "Brief written but delivery failed" "The plan exists but did not reach you. See $RECEIPT"
    STATUS=$SEND_STATUS
  fi
fi

# --------------------------------------------------------------------------
# BRIEF-UPDATE SAFETY NET. Added 2026-08-25, same principle as the delivery
# safety net above: do not trust the model to remember a step whose absence is
# invisible. Phase 2p is supposed to update the brief in place as each draft
# lands and re-run the notifier. When the watchdog fires mid-drafting it never
# gets there, and then the brief still lists the drafts as unchecked to-dos with
# no paths, so finished work reads as pending work.
#
# That is not hypothetical. On one early morning the run delivered the brief at 11:32,
# wrote 7 drafts between 11:35 and 11:42, was killed at 11:51, and never updated
# the brief. The owner read #32 and asked "where is the 1:1 prep brief?" It had
# existed on disk for two hours. Another run lost the grading of 5 drafts the same way.
#
# So: if drafts exist for today and the plan file is OLDER than the newest draft,
# the runner appends a factual index of what was produced and re-delivers. The
# notifier reuses today's brief id, so this never burns a number. This is a
# deterministic file listing, not a summary: it states paths and grades, and it
# deliberately does not try to describe the drafts, because the runner cannot read
# them and a fabricated summary would be worse than none.
# --------------------------------------------------------------------------
DRAFT_DIR="$WORKDIR/morning/drafts/$TODAY"
if [ -d "$DRAFT_DIR" ] && [ -n "$(ls -A "$DRAFT_DIR"/*.md 2>/dev/null)" ] && [ -f "$PLAN" ]; then
  NEWEST_DRAFT=$(ls -t "$DRAFT_DIR"/*.md 2>/dev/null | head -1)
  if [ -n "$NEWEST_DRAFT" ] && [ "$NEWEST_DRAFT" -nt "$PLAN" ]; then
    echo "brief-update: drafts are newer than the brief, appending the index and re-delivering" >> "$LOG"
    {
      printf '\n\n---\n\n## 🤖 DRAFTS PRODUCED THIS RUN (appended by run-prep.sh at %s)\n\n' "$(date '+%H:%M')"
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

    # Re-deliver so the notification and the rendered page carry the drafts too.
    # Same date, so the notifier reuses today's id rather than burning a new one.
    python3 "$NOTIFIER" --brief "$PLAN" --date "$TODAY" >> "$LOG" 2>&1 \
      || echo "brief-update: re-delivery failed, the appended index is still in the plan file" >> "$LOG"
  fi
fi

# ON-TIME RECORD. Lag between the scheduled fire and the first
# delivery, whether the runner delivered it or a person had to, classified
# unattended / late / missed against health.on_time.grace_minutes. Written into
# today's receipt and upserted as ONE run-log line per day, by the runner,
# because the model's own Phase 2c line is exactly what is missing on a bad day.
# Runs before the finished line, so this run's block is still open and counts.
python3 "$ONTIME" record --date "$TODAY" >> "$LOG" 2>&1 \
  || echo "on-time: ontime.py record failed, receipt left as it was" >> "$LOG"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') finished (exit $STATUS) =====" >> "$LOG"
exit $STATUS
