#!/usr/bin/env python3
"""setup.py: create the loop's folder inside a folder you already work in, or a new one.

Everything the loop writes lives in ONE subfolder, `morning/`, so an existing notes
or project folder stays exactly as it was. The package is linked in (copied where
links aren't allowed, e.g. Windows without Developer Mode), so `git pull` in the
package updates every workspace that uses it. Nothing of yours is ever overwritten:
anything already there is left alone and reported. See docs/LAYOUT.md.

    python3 scripts/setup.py ~/morning-brief               # a new folder
    python3 scripts/setup.py ~/notes --client opencode     # inside an existing one
    python3 scripts/setup.py ~/notes --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
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
TPL = PKG / "templates"

FOLDERS = ("briefs/rendered", "drafts", "notes", "examples", "state/receipts", "state/coach", "state/tmp")
LINKS = (("engine", PKG / "scripts"), ("package", PKG))
STARTERS = (
    ("config.yml", "config.template.yml"),
    ("profile.md", "profile.template.md"),
    ("goals.md", "goals.template.md"),
    ("state/ledger.md", "ledger.template.md"),
    ("state/coach/plan.md", "coach-plan.template.md"),
)


def find_working_python() -> str:
    """Find a working Python 3 interpreter. Tries py (Windows), python3, python, in order."""
    for cmd in (["py", "-3"], ["python3"], ["python"]):
        try:
            r = subprocess.run(cmd + ["-c", "import sys"], capture_output=True, timeout=2)
            if r.returncode == 0:
                # Verify it's Python 3.9+
                r = subprocess.run(cmd + ["-c", "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"],
                                  capture_output=True, timeout=2)
                if r.returncode == 0:
                    return " ".join(cmd)  # py -3, python3 or python
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return "python3"  # fallback


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", nargs="?", default="~/morning-brief")
    ap.add_argument("--client", choices=["claude", "opencode", "codex"], default=None)
    ap.add_argument("--copy", action="store_true", help="copy the package in instead of linking it")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true",
                    help="after a git pull: re-copy engine/ and package/ where they are copies, not links")
    a = ap.parse_args()

    ws = pathlib.Path(a.folder).expanduser()
    dry = a.dry_run
    if not dry:
        ws.mkdir(parents=True, exist_ok=True)
    ws = ws.resolve()
    if ws == PKG or PKG in ws.parents:
        print("✗ put your workspace outside the package folder, so a `git pull` can never touch your files.")
        return 2
    root = ws / "morning"
    existing = ws.exists() and any(p.name != "morning" for p in ws.iterdir()) if ws.exists() else False

    def say(m: str) -> None:
        print(f"  {m}")

    print("morning loop · setup")
    say(f"package: {PKG}")
    say(f"folder:  {ws}" + ("  (existing folder: only morning/ is added)" if existing else ""))

    print("\nfolders")
    for d in FOLDERS:
        p = root / d
        if p.is_dir():
            say(f"= morning/{d}")
        else:
            if not dry:
                p.mkdir(parents=True, exist_ok=True)
            say(f"+ morning/{d}")

    print("\nthe package, inside morning/")
    copied = []
    for name, target in LINKS:
        at = root / name
        if at.is_symlink():
            say(f"= morning/{name}" if at.resolve() == target.resolve() else f"! morning/{name} points elsewhere ({at.resolve()}); left alone")
            continue
        if at.exists():
            if a.refresh and not dry:
                # engine/ and package/ hold only package files; your own work lives elsewhere
                # in morning/, so a copied engine is safe to replace wholesale.
                shutil.rmtree(at)
                shutil.copytree(target, at, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "tests"))
                say(f"~ morning/{name} refreshed from the package")
            else:
                say(f"= morning/{name} (a copy; run with --refresh after a git pull)")
            continue
        if dry:
            say(f"+ morning/{name}")
            continue
        if not a.copy and not os.environ.get("MORNING_NO_SYMLINK"):
            try:
                at.symlink_to(target, target_is_directory=True)
                say(f"+ morning/{name} -> {target}")
                continue
            except (OSError, NotImplementedError):
                pass
        shutil.copytree(target, at, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "tests"))
        copied.append(name)
        say(f"+ morning/{name} (copied: links aren't available here)")

    print("\nyour files (only where none exists)")
    py_cmd = find_working_python()  # Find working interpreter once, before writing config
    for rel, src in STARTERS:
        at = root / rel
        if at.exists():
            say(f"= morning/{rel} (yours, untouched)")
            continue
        if not dry:
            text = (TPL / src).read_text(encoding="utf-8")
            text = text.replace("`last_reconciled: never`", f"`last_reconciled: {dt.date.today().isoformat()}`")
            if rel == "config.yml" and a.client:
                text = re.sub(r"^(  client:) \w+", rf"\1 {a.client}", text, count=1, flags=re.M)
            if rel == "config.yml" and sys.platform != "darwin":
                # macOS notifications don't exist elsewhere; the page is still made, and the
                # Windows runner adds a toast on top of it.
                text = re.sub(r"^(  channel:) macos", r"\1 file", text, count=1, flags=re.M)
            if rel == "config.yml":
                # Write the working Python interpreter so commands use the same one that setup.py found
                text = re.sub(r"^(  python:) python3", rf"\1 {py_cmd}", text, count=1, flags=re.M)
            at.parent.mkdir(parents=True, exist_ok=True)
            at.write_text(text, encoding="utf-8")
        say(f"+ morning/{rel}")
    for rel in ("state/run-log.md",):
        at = root / rel
        if not at.exists() and not dry:
            at.write_text("# Run log\n\nOne line per run, honest about what ran unattended.\n\n", encoding="utf-8")
    gi = root / ".gitignore"
    if not gi.exists():
        if not dry:
            gi.write_text("# Briefs, drafts and state hold text from your mail and chat. Keep all of morning/ out of git.\n*\n")
        say("+ morning/.gitignore (keeps your briefs and state out of git)")
    ob = root / "state/onboarding.json"
    if not ob.exists() and not dry:
        ob.write_text(json.dumps({"started": dt.date.today().isoformat(), "stages": {}}, indent=2) + "\n")

    print("\nnext")
    say(f"cd \"{ws}\"")
    say(f"{py_cmd} morning/engine/doctor.py         # proves the setup")
    say("then, in your AI client, from this folder: /onboard")
    if copied:
        say(f"Copied, not linked: {', '.join(copied)}. After each `git pull` of the package, run")
        say(f"python3 \"{PKG / 'scripts' / 'setup.py'}\" \"{ws}\" --refresh")
    if dry:
        print("\nDry run: nothing was written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
