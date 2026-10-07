#!/usr/bin/env python3
"""install.py: put the commands, skills and agents where your AI client loads them.

Clients load from different places, and a file in the wrong one is silently never
used, which looks exactly like a feature that doesn't work. So this script knows
each client's load paths, installs there, and never overwrites a file you changed:

    a file this package once shipped, unchanged  -> upgraded (old copy kept as .bak)
    a file you changed, or one we can't prove    -> KEPT; the new version goes beside it as .new
    a file of yours the package doesn't have     -> never touched

    python3 scripts/install.py                   # detect the client
    python3 scripts/install.py --client codex    # claude | opencode | codex
    python3 scripts/install.py --dry-run

Codex CLI: commands install as custom prompts (~/.codex/prompts) and skills into
~/.codex/skills. If your Codex version doesn't load skills, /morning reads them
straight from the package, so nothing breaks.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

PKG = pathlib.Path(__file__).resolve().parent.parent


def detect(home: pathlib.Path) -> str:
    env = os.environ.get("MORNING_CLIENT")
    if env in ("claude", "opencode", "codex"):
        return env
    for name in ("claude", "opencode", "codex"):
        if shutil.which(name):
            return name
    return "claude"


def targets(client: str, home: pathlib.Path) -> dict[str, pathlib.Path | None]:
    if client == "claude":
        return {"skills": home / ".claude/skills", "commands": home / ".claude/commands", "agents": home / ".claude/agents"}
    if client == "opencode":
        sk = home / ".config/opencode/skills"
        return {"skills": sk, "commands": sk, "agents": None}
    return {"skills": home / ".codex/skills", "commands": home / ".codex/prompts", "agents": None}


def stock(path: pathlib.Path) -> bool:
    """Did this package ever ship exactly this content? Proven with git, never guessed.
    No git (common on Windows), or a ZIP download with no history: nothing can be
    proven stock, so a changed file is always treated as yours and kept."""
    if not shutil.which("git"):
        return False
    if subprocess.run(["git", "-C", str(PKG), "rev-parse", "--git-dir"], capture_output=True).returncode:
        return False
    h = subprocess.run(["git", "hash-object", "--no-filters", str(path)], capture_output=True, text=True)
    return h.returncode == 0 and subprocess.run(
        ["git", "-C", str(PKG), "cat-file", "-e", h.stdout.strip()], capture_output=True).returncode == 0


def with_name(text: str, name: str) -> str:
    """A command installed as a skill needs `name:` in its frontmatter to register."""
    if text.startswith("---") and not re.search(r"^name:", text[:400], re.M):
        return text.replace("---\n", f"---\nname: {name}\n", 1)
    return text


def plan(client: str, home: pathlib.Path) -> list[tuple[str, str, pathlib.Path]]:
    """(kind, content, destination) for everything to install."""
    t = targets(client, home)
    out = []
    for src in sorted((PKG / "skills").glob("*/SKILL.md")):
        out.append(("skill", src.read_text(encoding="utf-8"), t["skills"] / src.parent.name / "SKILL.md"))
    for src in sorted((PKG / "commands").glob("*.md")):
        body = src.read_text(encoding="utf-8")
        if client == "opencode":
            out.append(("command", with_name(body, src.stem), t["commands"] / src.stem / "SKILL.md"))
        else:
            out.append(("command", body, t["commands"] / src.name))
    if t["agents"]:
        for src in sorted((PKG / "agents").glob("*.md")):
            if src.name != "README.md":
                out.append(("agent", src.read_text(encoding="utf-8"), t["agents"] / src.name))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--client", choices=["claude", "opencode", "codex"])
    ap.add_argument("--home", default=str(pathlib.Path.home()))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    home = pathlib.Path(a.home).expanduser()
    client = a.client or detect(home)

    print(f"morning loop · install for {client}{'  (dry run)' if a.dry_run else ''}")
    counts = {"added": 0, "upgraded": 0, "kept": 0, "current": 0}
    for kind, body, dest in plan(client, home):
        label = f"{kind:<8} {dest.parent.name if dest.name == 'SKILL.md' else dest.stem}"
        if dest.is_symlink():
            print(f"  = {label}: a link you made, left alone")
            continue
        if dest.exists():
            if dest.read_text(encoding="utf-8", errors="replace") == body:
                counts["current"] += 1
                continue
            if not stock(dest):
                if not a.dry_run:
                    dest.with_name(dest.name + ".new").write_text(body, encoding="utf-8")
                print(f"  ! {label}: yours (changed), KEPT. New version beside it as {dest.name}.new")
                counts["kept"] += 1
                continue
            if not a.dry_run:
                shutil.copy2(dest, dest.with_name(dest.name + ".bak"))
            print(f"  ~ {label}: upgraded (old copy at {dest.name}.bak)")
            counts["upgraded"] += 1
        else:
            print(f"  + {label}")
            counts["added"] += 1
        if not a.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body, encoding="utf-8")
    print(f"\n  added {counts['added']} · upgraded {counts['upgraded']} · yours kept {counts['kept']} · already current {counts['current']}")
    if client == "claude":
        print("  Restart Claude Code: agents load at session start.")
    print("\nNext: python3 scripts/setup.py <your folder>   (stage 0 of /onboard)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
