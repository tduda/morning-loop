#!/usr/bin/env python3
"""check_clean.py: fail if anything personal or private is in the package.

The package must carry no personal paths, no real email addresses, and nothing
from the place a contributor works. The generic checks below run for everyone.
Your own private terms (company, product, colleagues, internal ids) go in a file
outside the repo, one regex per line, so the list itself is never published:

    ~/.config/morning-loop/private-patterns.txt    (or set MORNING_PRIVATE_PATTERNS)

    python3 scripts/check_clean.py          # exit 1 on any hit
    python3 scripts/check_clean.py --list   # show the hits
"""
from __future__ import annotations

import os
import pathlib
import re
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", "node_modules"}
SKIP_FILES = {"check_clean.py", "LICENSE"}   # LICENSE carries the publisher's own name

GENERIC = [
    r"/Users/[a-z]+", r"/home/[a-z]+", r"C:\\Users\\[a-z]+",
    r"[a-z0-9._%+-]+@(?!example\.)[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}",
]
PRIVATE = pathlib.Path(os.environ.get("MORNING_PRIVATE_PATTERNS")
                       or pathlib.Path.home() / ".config/morning-loop/private-patterns.txt")


def patterns() -> list[str]:
    pats = list(GENERIC)
    if PRIVATE.is_file():
        pats += [ln.strip() for ln in PRIVATE.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")]
    return pats


def files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS) and p.name not in SKIP_FILES:
            yield p


def main() -> int:
    show = "--list" in sys.argv
    rx = re.compile("|".join(f"(?:{p})" for p in patterns()), re.I)
    hits = 0
    for p in files():
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in rx.finditer(line):
                hits += 1
                if show:
                    print(f"{p.relative_to(ROOT)}:{n}: {m.group(0)!r}  {line.strip()[:110]}")
    scope = "generic and private checks" if PRIVATE.is_file() else "generic checks only (no private patterns file)"
    if hits:
        print(f"✗ {hits} personal or private reference(s), {scope}. Run with --list to see them.")
        return 1
    print(f"✓ clean: {scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
