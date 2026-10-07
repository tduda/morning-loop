---
id: install
n: 0
title: Install
minutes: 5
optional: false
unlocks: "a working setup, checked end to end. Nothing personal yet."
brief_sample: |
  (no brief yet: this stage only proves the pieces are in place)
---
## What we do
1. Confirm the AI client: Claude Code, OpenCode or Codex CLI, logged in.
2. `python3 scripts/install.py` puts the commands, skills and agents where your client loads them, and never overwrites a file you changed.
3. Ask where the loop should live: **an existing folder you work in** (a notes or project folder) or **a new one** (default `~/morning`). Then `python3 scripts/setup.py <folder>` creates `morning/` inside it. It touches nothing else in that folder.

## Prove it works
`python3 morning/engine/doctor.py` from that folder prints ✓ for install, workspace and engine.

## Tell them
"You're set up. Nothing is connected yet, so the next stage, about you, is where the brief starts being yours. It takes 10 minutes and needs no tools."
