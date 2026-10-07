# Morning Loop ☀️

**A brief that's waiting for you every morning, made by an AI agent on your own computer from your own tools.**

Every weekday it reads what you connected (your tasks, calendar, meeting notes, inbox, chat), works out what's due, drafts what it can, and hands you one page: what changed, what needs you, and what's ready for your yes. You keep every decision. Nothing leaves your machine without your per-item approval.

It runs in the AI coding agent you already use: **Claude Code**, **OpenCode**, or **Codex CLI** (the local agent for ChatGPT users). Free and open source (MIT).

## You decide how far to go

Setup is a series of short stages. Each one says what it costs and what it adds, and proves it works before moving on. The tool stages can be skipped; stage 5 can't, because it's what makes the loop run itself. Stop any time; `/onboard` picks up where you left off.

| Stage | Time | You do | You get from then on |
|---|---|---|---|
| 0 · Install | 5 min | install, pick a folder | a working setup, checked end to end |
| 1 · About you | 10 min | role, timezone, top 3 goals, recurring meetings | **a brief every morning built on your goals, and a commitments list you add to just by talking. Works with zero tools connected.** |
| 2 · Your task tracker | 10 min | connect Jira, Linear, GitHub or Notion | what's assigned to you, what's stuck, what changed since yesterday |
| 3 · Calendar and meeting notes | 10 min | Google or Outlook calendar; Granola, Confluence, Notion or a notes folder | prep for today's meetings; yesterday's action items land in your list |
| 4 · Inbox and chat | 10 min | Gmail or Outlook; Slack or Teams | who's waiting on a reply from you; promises you made in threads, tracked |
| 5 · Make it automatic (required) | 5 min | schedule it | **the loop runs itself**: the brief is waiting when you open your laptop, nothing to type |
| 6 · Your recurring jobs | 20 min | a short interview about your recurring work | drafts of your weekly update, meeting prep and follow-ups, checked against a quality bar, sent only with your yes |
| 7 · Metrics (optional) | 10 min | Amplitude, GA4, Mixpanel or PostHog | a daily pulse on the numbers you choose |

## Quick start

**New to terminals or VS Code?** Follow [`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md): about 20 minutes on a Mac or a Windows PC, step by step.

Otherwise: you need Python 3.9+ and one of the clients above, installed and logged in. Download ([ZIP](https://github.com/tduda/morning-loop/archive/refs/heads/main.zip)) or clone this repo (`git clone https://github.com/tduda/morning-loop.git`), then double-click **Start here - Mac.command** or **Start here - Windows.bat**, or run:

```bash
python3 scripts/quickstart.py          # Mac and Linux
py scripts\quickstart.py               # Windows
```

It installs the commands into your client, asks where your brief should live, sets that folder up and checks it. Then open that folder in VS Code (or your client's app or a terminal) and type **`/onboard`**.

**Already have a folder you work in** (notes, a project)? Give its path when asked. The loop adds one subfolder, `morning/`, and touches nothing else.

## Good to know

- **The brief is made on your computer, so it arrives when your computer is on**: at 07:52, or the first time you open it that morning. There's no server, and your data stays on your machine and in the tools you connect.
- **Read-only first.** Every connector guide prefers read-only access. The loop drafts replies, tasks and updates; sending any of them needs your yes, every time.
- **Honest by design.** Every claim in the brief carries a marker: verified (re-checked by a separate agent), reported, inferred or carried from an earlier day. Numbers it can't source say "not checked" instead of guessing.
- **Drafts get good with your examples.** Drop two or three of your own past weekly updates (or meeting notes, or whatever the job produces) into `morning/examples/<skill>/` and the drafts start sounding like you.

## What works where

| | Claude Code | OpenCode | Codex CLI |
|---|---|---|---|
| Onboarding, brief, drafts | ✓ | ✓ | ✓ |
| Independent verifier agents | ✓ | checks run inline, claims marked "reported" | checks run inline, claims marked "reported" |
| Install and setup | ✓ Mac; Windows written for it, not yet run on a real PC | same | same |
| Scheduled runner | ✓ Mac, Linux; Windows written, not yet run on a real PC | Mac and Linux, not yet live-tested | Mac and Linux, not yet live-tested |

Which tools connect to which client, and how, is in [`connectors/README.md`](connectors/README.md). A few combinations aren't possible yet (for example Slack in OpenCode); the guides say so plainly.

## Status

**Beta.** The engine (the trust layer, the questions file, the meeting-action queue, delivery, on-time tracking) comes from a loop run daily since mid-2026. This standalone version is new. What's been tested: a full rehearsal (`tests/run.py`: install for all three clients, setup in an existing folder, the onboarding map, and every runner with stand-in clients) and a real Claude Code run that produced a first brief for a test persona at stage 1. Not yet tested: the interactive `/onboard` conversation with a real newcomer, the tool stages against live accounts, and the OpenCode, Codex and Windows runners on real installs. Please open an issue with what happened on yours.

## Repo map

```
commands/    /onboard, /morning, /brief, /tickets, /shipped, /coach
stages/      the onboarding stages: cost, what each unlocks, how it's proven
connectors/  one guide per tool, per client, with a test read
skills/      today, meeting-prep, meeting-debrief, weekly-update, inbox-triage, stall-check, jobs-interview, metrics-pulse
rubrics/     the quality bar each drafter is graded against
roles/       optional presets that shape the brief to your role
agents/      read-only verifier agents (Claude Code)
scripts/     install, setup, doctor, onboarding map, the engine, schedulers
docs/        GETTING-STARTED.md (for beginners), LAYOUT.md, SCHEDULE.md (stage 5)
```

## Contributing

Issues and pull requests are welcome. Before committing, run `python3 scripts/check_clean.py` (it keeps the package free of anyone's personal or company context) and `python3 tests/run.py`.

## License

MIT. See [`LICENSE`](LICENSE).
