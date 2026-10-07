# Make the brief automatic (stage 5)

**The brief is made on your computer, so it arrives when your computer is on.** There is no server. The loop runs at 07:52 on weekdays, and if your computer is closed or asleep then, it runs the first time you open it that morning (a catch-up keeps trying every 15 minutes until 12:00). A computer that stays shut all morning gets no brief that day, and the next brief's health line says so.

Two scheduled jobs do this:

| job | when | what it does |
|---|---|---|
| prep | 07:52 on weekdays | makes today's brief |
| catch-up | at login, and every 15 minutes | does nothing unless it's a weekday, between 07:45 and 12:00, and no brief has landed yet |

A lock means the two can never run at the same time as each other, or as a `/morning` you started yourself.

## Pick your runner

| your client | runner template (in `morning/engine/`) |
|---|---|
| Claude Code | `run-prep.template.sh` (Mac/Linux) or `run-prep.template.ps1` (Windows) |
| OpenCode | `run-prep.opencode.template.sh` |
| Codex CLI | `run-prep.codex.template.sh` |

Every runner waits for the network before starting, keeps the machine awake while it works, counts only awake time against its time limit, delivers the brief itself if the run forgot to, and records whether the brief was on time.

## Mac

Run these from your workspace folder (the one containing `morning/`).

```sh
# 1. your runner, with your folder filled in (pick the template for your client)
sed "s|<PATH TO YOUR WORKSPACE>|$PWD|" morning/engine/run-prep.template.sh > morning/state/run-prep.sh

# 2. the two launchd jobs (absolute paths only: a plist has no ~)
for job in prep catchup; do
  sed -e "s|__RUN_PREP_PATH__|$PWD/morning/state/run-prep.sh|" \
      -e "s|__LOG_PATH__|$PWD/morning/state/runner.stdout.log|" \
      morning/engine/com.morning-loop.$job.plist.template > com.morning-loop.$job.plist
  plutil -lint com.morning-loop.$job.plist      # must say OK
done

# 3. ONE supervised run first. Don't hand a scheduler something you haven't watched work.
zsh morning/state/run-prep.sh; echo "exit $?"
tail -20 morning/state/runner.log

# 4. then schedule both
for job in prep catchup; do
  mv com.morning-loop.$job.plist ~/Library/LaunchAgents/
  launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.morning-loop.$job.plist
done
launchctl list | grep morning-loop             # expect exactly two
```

Want the brief waiting when you sit down, even with the lid closed overnight? Keep the Mac on power and schedule a wake: `sudo pmset repeat wakeorpoweron MTWRF 07:45:00`.

Remove: `launchctl bootout gui/$UID/com.morning-loop.prep` and the same for `catchup`.

## Windows

The `.sh` runners need a Unix shell; Windows uses the PowerShell runner and Task Scheduler. **The Windows runner has not yet run on a real Windows machine.** Do the supervised run in step 2 and tell us what happened.

```powershell
# 1. your runner: copy it and fill in $WorkDir (and $Claude / $Python if they live elsewhere)
Copy-Item morning\engine\run-prep.template.ps1 morning\state\run-prep.ps1
notepad morning\state\run-prep.ps1

# 2. ONE supervised run
powershell -NoProfile -ExecutionPolicy Bypass -File .\morning\state\run-prep.ps1; "exit $LASTEXITCODE"
Get-Content morning\state\runner.log -Tail 20

# 3. register both tasks (per user, no admin)
Copy-Item morning\engine\register-prep-task.template.ps1 morning\state\register-prep-task.ps1
notepad morning\state\register-prep-task.ps1     # fill $RunPrep with the full path of your run-prep.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\morning\state\register-prep-task.ps1
Get-ScheduledTask -TaskName MorningLoop-*          # expect exactly two
```

## Linux

First, create your runner:

```sh
sed "s|<PATH TO YOUR WORKSPACE>|$PWD|" morning/engine/run-prep.template.sh > morning/state/run-prep.sh
chmod +x morning/state/run-prep.sh
zsh morning/state/run-prep.sh; echo "exit $?"     # supervised run first (needs zsh)
tail -20 morning/state/runner.log
```

Then, pick one: **cron** (traditional) or **systemd timer** (modern, recommended for recent Linux).

### cron (traditional, any Linux)

```sh
crontab -e
# add:
# 52 7 * * 1-5   zsh /full/path/morning/state/run-prep.sh
# */15 7-11 * * 1-5   zsh /full/path/morning/state/run-prep.sh --if-missing
```

### systemd timer (modern Linux, recommended)

Create two timer files in `~/.config/systemd/user/`:

**morning-loop-prep.timer:**
```ini
[Unit]
Description=Morning Loop brief preparation
After=network-online.target
Wants=network-online.target

[Timer]
OnCalendar=Mon-Fri *-*-* 07:52:00
Unit=morning-loop-prep.service
Persistent=true

[Install]
WantedBy=timers.target
```

**morning-loop-prep.service:**
```ini
[Unit]
Description=Morning Loop brief preparation
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/zsh /full/path/morning/state/run-prep.sh
StandardOutput=append:/full/path/morning/state/runner.log
StandardError=append:/full/path/morning/state/runner.log
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
```

**morning-loop-catchup.timer:**
```ini
[Unit]
Description=Morning Loop catch-up (retry if missed)
After=network-online.target
Wants=network-online.target

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min
Unit=morning-loop-catchup.service
Persistent=true

[Install]
WantedBy=timers.target
```

**morning-loop-catchup.service:**
```ini
[Unit]
Description=Morning Loop catch-up

[Service]
Type=oneshot
ExecStart=/usr/bin/zsh /full/path/morning/state/run-prep.sh --if-missing
StandardOutput=append:/full/path/morning/state/runner.log
StandardError=append:/full/path/morning/state/runner.log
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
```

Then enable:
```sh
systemctl --user daemon-reload
systemctl --user enable morning-loop-prep.timer morning-loop-catchup.timer
systemctl --user start morning-loop-prep.timer morning-loop-catchup.timer
systemctl --user list-timers morning-loop-*     # check they're active
```

## Delivery

`delivery.channel` in `morning/config.yml`:

- `macos` (default on Mac): a notification, and the brief opens as a local page.
- `file`: the page is written to `morning/briefs/rendered/`, nothing is pushed. You open it yourself.
- `slack`: posts the one-line summary to a Slack webhook you own. Put the webhook URL in your environment (`MORNING_SLACK_WEBHOOK`), never in the config file.

The catch-up stops as soon as today's brief exists (`sent`, or `rendered_not_sent` on the file channel).

## Did it work?

`python3 morning/engine/ontime.py report` prints how many recent weekdays the brief arrived on its own, late, or not at all. The same line is in every brief's HEALTH section.
