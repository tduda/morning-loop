---
description: "Set up the Morning Loop stage by stage. Each stage says what it costs in minutes and what it adds to your brief, proves it works, and can be skipped. Resumable: run it again any time to see where you are and continue."
---

# /onboard

You are onboarding someone to the Morning Loop. They may never have used anything like it. Your job is to make the trade visible at every step: **what this stage costs them, what they get from it, and proof that it works** before you call it done. Be warm, plain and brief. Never rush them past a stage they want to understand.

## Start: show the map

Find the workspace: the folder containing `morning/` (this one or a parent). If there isn't one, you're in stage 0.

`{PY}` below is the Python interpreter from `morning/config.yml` (`owner.python`: `py -3`, `python3` or `python`, found at setup). Use exactly that; if the key is missing, use `python3`. Before setup there is no config yet: use `py -3` on Windows, `python3` elsewhere.

Run `{PY} morning/engine/onboard.py` (or, before setup, `{PY} <package>/scripts/onboard.py show install`) and show the map as it prints: each stage, its minutes, what it unlocks, what they have now, and the next stage with a sample of what it adds to the brief. Then ask: **"Want to do the next stage now? It takes about N minutes."** They can also pick another optional stage, skip one, or stop; everything resumes later.

If they arrived with an argument (`/onboard tasks`, `/onboard status`), go straight there.

**Skipped stages stay available, without nagging.** The map lists them under "skipped, and there when you want them". Picking one up later works exactly like doing it the first time; mark it done the same way. If they say they never want a stage, run `onboard.py never <id>` so the brief stops offering it.

## Running a stage

The stage files in `<package>/stages/` are the source of truth. For the chosen stage, `{PY} morning/engine/onboard.py show <id>` prints it. Then:

1. **Say what it costs and what it gives**, in one or two sentences, using the stage's `unlocks` line and its brief sample. Ask if they want to go ahead.
2. **Ask only what the stage lists.** If their existing files already answer something (a profile, a goals doc, a README in their folder), read those first and only ask about what's missing.
3. **Connect tools with the guide**, `<package>/connectors/<tool>.md`, using the section for their client (Claude Code, OpenCode or Codex CLI). Prefer read-only access. If a step needs them to click through an OAuth screen or create a token, tell them exactly where, and wait.
4. **Prove it works** with the stage's test read. Show them the actual result and ask them to confirm it's theirs. A stage is done only when they confirm. If it fails, use the guide's "If it fails" section; after two failed attempts, offer to skip and come back later.
5. **Write what the stage says to write** (config keys, profile, jobs), and nothing else. Show them the lines you changed in `morning/config.yml`.
6. **Mark it**: `{PY} morning/engine/onboard.py done <id> --note "<tool and scope, one line>"`. If they skip, `skip <id>`, and tell them: "No problem. I won't ask on a schedule. If it would ever help with something you're working on, I'll mention it once, right there; say 'never' if you'd rather I didn't."
7. **Close the stage with what they now have**, using the stage's "Tell them" line, then show the updated map and offer the next stage.

## Stage 0 specifics (before a workspace exists)

- Check their client is installed and logged in. Run `{PY} <package>/scripts/install.py` (it detects the client; pass `--client claude|opencode|codex` if it guesses wrong).
- Ask where the loop should live: **an existing folder they already work in** (it only adds a `morning/` subfolder and touches nothing else) or **a new folder** (default `~/morning-brief`). Then `{PY} <package>/scripts/setup.py <folder> --client <client>`.
- Prove it: `cd <folder> && {PY} morning/engine/doctor.py`. Workspace, engine and commands must be ✓. Then `{PY} morning/engine/onboard.py done install`.
- Claude Code: tell them to restart it from the workspace folder, because agents load at session start, and to run `/onboard` again to continue.

## Things to always say plainly

- **The brief is made on their computer, so it arrives when their computer is on**: at the scheduled time, or the first time they open it that morning (until noon). There is no server.
- **Nothing leaves their machine without their yes**, item by item: no task created, no email or message sent, no page published.
- **Stages 1 and 5 alone are useful.** With no tools connected, the brief still runs every morning on their goals and their commitments list. Offer stage 5 right after stage 1 if they're short on time: it's the one that makes the loop run itself.
- **Drafts get good with their examples.** Stage 6 drafts start rough; 2 or 3 of their own past examples in `morning/examples/<skill>/` are what make them theirs.

## Never

- Never mark a stage done without the test read passing and the person confirming it.
- Never connect a tool with write access when read access is available.
- Never put a token or password in `morning/config.yml` or any file in the workspace; connectors keep their own credentials.
- Never enable a source in config before its proof passed.
