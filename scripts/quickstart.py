#!/usr/bin/env python3
"""quickstart.py: the guided first install, for Mac and Windows alike.

Double-click "Start here - Mac.command" or "Start here - Windows.bat" in the repo,
or run `python3 scripts/quickstart.py` (Windows: `py scripts\\quickstart.py`).
It finds your AI client, installs the commands into it, asks where your brief
should live, sets that folder up, checks it, and tells you exactly what to open
next. It changes nothing outside that folder and your client's own folders.

Non-interactive (for scripts and tests): MORNING_QS_CLIENT=claude MORNING_QS_FOLDER=~/morning-brief
"""
from __future__ import annotations

import os
import pathlib
import platform
import shutil
import subprocess
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PKG = pathlib.Path(__file__).resolve().parent.parent
WIN = platform.system() == "Windows"
PY = "py" if WIN else "python3"

CLIENTS = {
    "claude": {"name": "Claude Code", "cmd": "claude",
               "install": "https://code.claude.com/docs/en/setup",
               "vscode": "the Claude Code extension (search 'Claude Code' in VS Code's Extensions panel)"},
    "codex": {"name": "Codex CLI (for ChatGPT plans)", "cmd": "codex",
              "install": "https://learn.chatgpt.com/docs/codex/cli",
              "vscode": "the Codex extension (search 'Codex' in VS Code's Extensions panel)"},
    "opencode": {"name": "OpenCode", "cmd": "opencode",
                 "install": "https://opencode.ai/docs",
                 "vscode": "VS Code's built-in terminal (Terminal > New Terminal), then type: opencode"},
}


def ask(prompt: str, default: str = "") -> str:
    try:
        ans = input(f"{prompt} ").strip()
    except EOFError:
        ans = ""
    return ans or default


def main() -> int:
    print("\n☀️  Morning Loop · quick start\n")
    if sys.version_info < (3, 9):
        print(f"Python {sys.version.split()[0]} is too old. Install Python 3.9 or newer from https://www.python.org/downloads/")
        return 1

    # 1. which client
    found = [k for k, c in CLIENTS.items() if shutil.which(c["cmd"])]
    client = os.environ.get("MORNING_QS_CLIENT")
    if not client:
        if not found:
            print("No AI client found yet. Install one of these, log in once, then run this again:\n")
            for c in CLIENTS.values():
                print(f"  · {c['name']}: {c['install']}")
            print("\nNot sure which? If you have a Claude subscription, pick Claude Code. If you have a ChatGPT plan, pick Codex CLI.")
            return 1
        if len(found) == 1:
            client = found[0]
            print(f"Found {CLIENTS[client]['name']}. Using it.")
        else:
            print("Found more than one AI client:")
            for i, k in enumerate(found, 1):
                print(f"  {i}. {CLIENTS[k]['name']}")
            pick = ask(f"Which one should run your brief? [1-{len(found)}, Enter for 1]", "1")
            client = found[int(pick) - 1] if pick.isdigit() and 1 <= int(pick) <= len(found) else found[0]

    # 2. install commands and skills into it
    print(f"\n1/3 · Installing into {CLIENTS[client]['name']} ...")
    r = subprocess.run([sys.executable, str(PKG / "scripts" / "install.py"), "--client", client])
    if r.returncode:
        print("The install step failed; the messages above say why.")
        return 1

    # 3. where the brief lives
    default = str(pathlib.Path.home() / "morning-brief")
    print("\n2/3 · Where should your morning brief live?")
    print("   Press Enter for a new folder, or paste the path of a folder you already work in")
    print("   (notes, a project). In an existing folder it only adds one subfolder, morning/.")
    folder = os.environ.get("MORNING_QS_FOLDER") or ask(f"   Folder [Enter for {default}]:", default)
    folder = str(pathlib.Path(folder.strip().strip('"').strip("'")).expanduser())
    r = subprocess.run([sys.executable, str(PKG / "scripts" / "setup.py"), folder, "--client", client])
    if r.returncode:
        return 1

    # 4. check it
    print("\n3/3 · Checking ...")
    r = subprocess.run([sys.executable, "morning/engine/doctor.py"], cwd=folder)

    c = CLIENTS[client]
    print("\n" + "─" * 60)
    print("You're set up. One step left, and it's the friendly one:\n")
    print(f"  1. Open this folder: {folder}")
    print(f"       In VS Code: File > Open Folder..., pick it, then open {c['vscode']}.")
    print(f"       No VS Code? Open a terminal in that folder and type: {c['cmd']}")
    print("  2. Type  /onboard  and press Enter.")
    print("\nIt walks you through stage 1 (about you, 10 minutes, no tools needed) and shows")
    print("what every later stage adds, so you decide how far to go.")
    if client == "claude":
        print("\n(If Claude Code was already open, restart it so it picks up the new commands.)")
    if WIN:
        print("\nOn Windows the brief is saved as a page you open; there are no notifications yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
