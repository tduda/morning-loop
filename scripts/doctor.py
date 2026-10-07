#!/usr/bin/env python3
"""doctor.py: is this setup able to do what its config says?

A config can describe coverage that doesn't exist: a job naming a skill that never
loads, a source switched on with no connector, a schedule nobody loaded. Each of
those fails silently at run time, so this checks them before you rely on them.

    cd <your folder> && python3 morning/engine/doctor.py
    python3 morning/engine/doctor.py --json
Exit 0: nothing blocking. Exit 1: something the loop needs is missing (named, with the fix).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import re
import subprocess
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE.parent
SOURCES = ("tasks", "calendar", "meetings", "inbox", "chat", "metrics")
LOAD = {
    "claude": ("{home}/.claude/skills/{n}/SKILL.md", "{home}/.claude/commands/{n}.md"),
    "opencode": ("{home}/.config/opencode/skills/{n}/SKILL.md",),
    "codex": ("{home}/.codex/skills/{n}/SKILL.md", "{home}/.codex/prompts/{n}.md"),
}


def workspace() -> pathlib.Path | None:
    cwd = pathlib.Path.cwd()
    return next((p for p in [cwd, *cwd.parents] if (p / "morning" / "state").is_dir()), None)


def load_config(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except ImportError:
        return fallback_parse(text)


def fallback_parse(text: str) -> dict:
    """Enough of YAML for this config without PyYAML: nested maps, scalars, and a
    list of flat maps under `jobs:`."""
    cfg: dict = {}
    stack: list[tuple[int, dict]] = [(-1, cfg)]
    jobs: list[dict] | None = None
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        ind = len(line) - len(line.lstrip())
        s = line.strip()
        if s.startswith("- ") and jobs is not None:
            jobs.append({})
            s = s[2:]
        if jobs is not None and ind >= 2 and jobs and ":" in s and not s.endswith(":"):
            k, v = s.split(":", 1)
            jobs[-1][k.strip()] = clean(v)
            continue
        while stack and stack[-1][0] >= ind:
            stack.pop()
        k, _, v = s.partition(":")
        k = k.strip()
        if k == "jobs" and ind == 0:
            jobs = []
            cfg["jobs"] = jobs
            continue
        if ind == 0:
            jobs = None
        if v.strip() == "":
            d: dict = {}
            stack[-1][1][k] = d
            stack.append((ind, d))
        else:
            stack[-1][1][k] = clean(v)
    return cfg


def clean(v: str):
    v = v.strip().strip('"')
    return {"true": True, "false": False, "null": None, "": ""}.get(v, v)


def resolve_skill(name: str, client: str, home: pathlib.Path) -> str:
    for tpl in LOAD.get(client, ()):
        if pathlib.Path(tpl.format(home=home, n=name)).is_file():
            return "ok"
    if (PKG / "skills" / name / "SKILL.md").is_file() or (PKG / "commands" / f"{name}.md").is_file():
        return "NOT INSTALLED"
    return "MISSING"


def schedule_loaded() -> str:
    system = platform.system()
    try:
        if system == "Darwin":
            out = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
            n = len([ln for ln in out.splitlines() if "morning-loop" in ln])
            return f"{n} launchd job(s)" + ("" if n == 2 else " (expected 2: prep and catch-up)")
        if system == "Windows":
            out = subprocess.run(["schtasks", "/Query", "/FO", "LIST"], capture_output=True, text=True).stdout
            n = out.count("MorningLoop-")
            return f"{n} scheduled task(s)" + ("" if n == 2 else " (expected 2)")
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        return f"{out.count('run-prep')} cron line(s)"
    except FileNotFoundError:
        return "could not check on this system"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--home", default=str(pathlib.Path.home()))
    a = ap.parse_args()
    home = pathlib.Path(a.home).expanduser()
    rows: list[tuple[str, str, str, str]] = []   # (section, item, state, fix)
    blocked = 0

    def add(section, item, state, fix="", block=False):
        nonlocal blocked
        rows.append((section, item, state, fix))
        blocked += int(block)

    ws = workspace()
    if ws is None:
        add("workspace", "morning/ folder", "NOT FOUND", "run python3 scripts/setup.py <folder>, then run this from that folder", True)
        return report(rows, blocked, a.json, None)
    root = ws / "morning"
    add("workspace", str(ws), "ok")
    for name in ("engine", "package"):
        p = root / name
        if not p.exists() and p.is_symlink():
            # Symlink points to a target that no longer exists
            add("workspace", f"morning/{name}", "BROKEN LINK",
                f"the symlink points to a missing target. Run python3 scripts/setup.py {ws} --refresh", True)
        else:
            add("workspace", f"morning/{name}", "ok" if p.exists() else "MISSING",
                "" if p.exists() else "re-run python3 scripts/setup.py on this folder", not p.exists())

    cfg_path = pathlib.Path(os.environ.get("MORNING_CONFIG") or root / "config.yml")
    if not cfg_path.is_file():
        add("config", str(cfg_path), "MISSING", "re-run setup.py", True)
        return report(rows, blocked, a.json, ws)
    cfg = load_config(cfg_path)
    owner = cfg.get("owner") or {}
    client = owner.get("client") or "claude"
    add("config", "owner", "ok" if owner.get("name") and owner.get("timezone") else "not filled yet",
        "" if owner.get("name") else "stage 1 of /onboard fills it")

    srcs = cfg.get("sources") or {}
    for s in SOURCES:
        b = srcs.get(s) or {}
        if not b.get("enabled"):
            add("sources", s, "off")
            continue
        tool = b.get("tool") or ""
        guide = (PKG / "connectors" / f"{tool}.md").is_file()
        add("sources", f"{s} ({tool or 'no tool'})", "on" if tool else "ON BUT NO TOOL",
            "" if tool else f"set sources.{s}.tool, or switch it off", not tool)
        if tool and not guide:
            add("sources", f"{s} guide", f"no connectors/{tool}.md", "fine if you connected it yourself")

    for job in cfg.get("jobs") or []:
        skill = job.get("skill")
        if not skill:
            add("jobs", job.get("id", "?"), "inline")
            continue
        st = resolve_skill(skill, client, home)
        fix = {"NOT INSTALLED": f"python3 {PKG}/scripts/install.py --client {client}",
               "MISSING": "no such skill anywhere: fix the name or comment the job out"}.get(st, "")
        add("jobs", f"{job.get('id')} -> {skill}", st, fix, st == "MISSING")
        if st == "NOT INSTALLED" and client == "codex":
            rows[-1] = ("jobs", f"{job.get('id')} -> {skill}", "read from package", "Codex reads it from morning/package/skills")
        if (job.get("output") == "draft") and not (PKG / "rubrics" / f"{skill}.rubric.yml").is_file():
            add("jobs", f"{skill} rubric", "_base only", "it will be graded on the general checks until it has its own rubric")
    for cmd in ("morning", "onboard"):
        st = resolve_skill(cmd, client, home)
        add("commands", f"/{cmd}", st, "" if st == "ok" else f"python3 {PKG}/scripts/install.py --client {client}", st != "ok")

    sched = cfg.get("schedule") or {}
    add("schedule", "brief made automatically", schedule_loaded() if sched.get("enabled") else "off (stage 5)")
    ob = root / "state" / "onboarding.json"
    if ob.is_file():
        done = [k for k, v in json.loads(ob.read_text()).get("stages", {}).items() if v.get("status") == "done"]
        add("onboarding", "stages done", f"{len(done)} of 8" + (f": {', '.join(done)}" if done else ""))
    return report(rows, blocked, a.json, ws)


def report(rows, blocked, as_json, ws) -> int:
    if as_json:
        print(json.dumps({"workspace": str(ws) if ws else None, "blocked": blocked,
                          "checks": [dict(zip(("section", "item", "state", "fix"), r)) for r in rows]}, indent=2))
        return 1 if blocked else 0
    print("\nMORNING LOOP DOCTOR")
    section = None
    for sec, item, state, fix in rows:
        if sec != section:
            print(f"\n{sec.upper()}")
            section = sec
        ok = state in ("ok", "on", "off", "inline") or state.startswith(("off", "1 ", "2 ", "0 of", "read from"))
        mark = "✓" if ok else ("✗" if state.isupper() or state.startswith(("NOT", "MISSING", "ON BUT")) else "·")
        print(f"  {mark} {item:<36} {state}")
        if fix:
            print(f"      fix: {fix}")
    print()
    if blocked:
        print(f"✗ {blocked} thing(s) the loop needs are missing. Each one fails silently at run time.")
        return 1
    print("✓ nothing blocking. Run /onboard (or /morning) from this folder.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
