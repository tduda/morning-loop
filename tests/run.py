#!/usr/bin/env python3
"""tests/run.py: rehearse a newcomer's whole setup in a throwaway folder.

Nothing touches your real home or workspace: every step uses a temporary HOME and
a temporary workspace, stand-in clients instead of real ones, and the `file`
delivery channel so no notification pops up.

    python3 tests/run.py
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

PKG = pathlib.Path(__file__).resolve().parent.parent
S = PKG / "scripts"
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✓' if ok else '✗'} {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def run(cmd, cwd=None, env=None, timeout=300) -> subprocess.CompletedProcess:
    e = dict(os.environ, **(env or {}))
    return subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True, timeout=timeout)


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="morning-loop-test-"))
    print(f"rehearsal in {tmp}\n")

    print("package")
    r = run([sys.executable, S / "check_clean.py"])
    check("no company or personal context", r.returncode == 0, r.stdout.strip()[-200:])
    for f in S.glob("*.py"):
        r = run([sys.executable, "-m", "py_compile", str(f)])
        check(f"compiles: {f.name}", r.returncode == 0, r.stderr[-200:])
    zsh = shutil.which("zsh")
    if not zsh:
        print("  - shell syntax: skipped, zsh is not installed (the runners are zsh scripts)")
    for sh in (list(S.glob("*.sh")) + list(S.glob("run-prep*.template.sh"))) if zsh else []:
        r = run([zsh, "-n", str(sh)])
        check(f"shell syntax: {sh.name}", r.returncode == 0, r.stderr[-200:])
    skills = {p.parent.name for p in (PKG / "skills").glob("*/SKILL.md")}
    for p in (PKG / "skills").glob("*/SKILL.md"):
        head = p.read_text()[:600]
        check(f"skill frontmatter: {p.parent.name}", head.startswith("---") and "description:" in head)
    tpl = (PKG / "templates" / "config.template.yml").read_text()
    for sk in [s for s in re.findall(r"^\s+skill: ([a-z-]+)", tpl, re.M) if s != "null"]:
        check(f"config template skill exists: {sk}", sk in skills)
    for role in (PKG / "roles").glob("*.yml"):
        for sk in re.findall(r"skill: ([a-z-]+)", role.read_text()):
            check(f"role {role.stem} skill exists: {sk}", sk in skills)
    for st in (PKG / "stages").glob("*.md"):
        for tool in re.findall(r"connectors/([a-z-]+)\.md", st.read_text()):
            check(f"stage {st.stem} guide exists: {tool}", tool == "<tool>" or (PKG / "connectors" / f"{tool}.md").is_file())

    print("\nengine self-tests")
    ws0 = tmp / "selftest"
    (ws0 / "morning" / "state").mkdir(parents=True)
    for script in ("trust", "ontime", "tickets", "asks", "coach", "sharpen"):
        r = run([sys.executable, S / f"{script}.py", "selftest"], cwd=ws0)
        check(f"{script}.py selftest", r.returncode == 0, (r.stdout + r.stderr).strip()[-300:])

    print("\ninstall, per client")
    for client in ("claude", "opencode", "codex"):
        home = tmp / f"home-{client}"
        r = run([sys.executable, S / "install.py", "--client", client, "--home", str(home)])
        check(f"{client}: install runs", r.returncode == 0, r.stderr[-200:])
        loads = {"claude": home / ".claude/commands/morning.md",
                 "opencode": home / ".config/opencode/skills/morning/SKILL.md",
                 "codex": home / ".codex/prompts/morning.md"}[client]
        check(f"{client}: /morning lands where the client loads it", loads.is_file())
        r = run([sys.executable, S / "install.py", "--client", client, "--home", str(home)])
        check(f"{client}: re-install changes nothing", "added 0 · upgraded 0 · yours kept 0" in r.stdout, r.stdout[-200:])
    home = tmp / "home-claude"
    mine = home / ".claude/skills/weekly-update/SKILL.md"
    mine.write_text(mine.read_text() + "\n- my own rule\n")
    r = run([sys.executable, S / "install.py", "--client", "claude", "--home", str(home)])
    check("a skill you changed is kept", "- my own rule" in mine.read_text())
    check("the new version goes beside it as .new", mine.with_name("SKILL.md.new").is_file())

    print("\nsetup inside an existing folder")
    notes = tmp / "notes"
    notes.mkdir()
    (notes / "ideas.md").write_text("my ideas\n")
    r = run([sys.executable, S / "setup.py", str(notes), "--client", "claude"])
    check("setup runs", r.returncode == 0, r.stderr[-200:])
    check("your existing files untouched", (notes / "ideas.md").read_text() == "my ideas\n"
          and sorted(p.name for p in notes.iterdir()) == ["ideas.md", "morning"])
    for rel in ("config.yml", "profile.md", "goals.md", "state/ledger.md", "state/onboarding.json", "engine/doctor.py",
                "package/stages/1-about-you.md"):
        check(f"morning/{rel}", (notes / "morning" / rel).exists())
    r = run([sys.executable, "morning/engine/doctor.py", "--home", str(home)], cwd=notes)
    check("doctor passes after install + setup", r.returncode == 0, r.stdout[-400:])
    r = run([sys.executable, S / "setup.py", str(notes)])
    check("setup again keeps your config", "= morning/config.yml (yours, untouched)" in r.stdout)

    print("\nonboarding map")
    ob = ["python3", "morning/engine/onboard.py"]
    r = run(ob, cwd=notes)
    check("map shows stage 0 next", "→ 0  Install" in r.stdout, r.stdout[:300])
    run(ob + ["done", "install"], cwd=notes)
    r = run(ob + ["skip", "about_you"], cwd=notes)
    check("stage 1 can't be skipped", r.returncode == 2)
    r = run(ob + ["skip", "schedule"], cwd=notes)
    check("stage 5 can't be skipped, and says why", r.returncode == 2 and "run itself" in r.stdout)
    run(ob + ["done", "about_you", "--note", "test"], cwd=notes)
    r = run(ob + ["skip", "metrics"], cwd=notes)
    r = run(ob + ["--json"], cwd=notes)
    st = {s["id"]: s["status"] for s in json.loads(r.stdout)["stages"]}
    check("stage states recorded", st["install"] == "done" and st["about_you"] == "done"
          and st["tasks"] == "next" and st["metrics"] == "skipped", str(st))
    r = run(ob, cwd=notes)
    check("map lists what you have now", "WHAT YOU HAVE NOW" in r.stdout and "built on your goals" in r.stdout)

    print("\nskipped stages: offered only with a reason, and rarely")
    obj = notes / "morning/state/onboarding.json"
    run(ob + ["skip", "tasks"], cwd=notes)
    due = lambda: [d["id"] for d in json.loads(run(ob + ["revisit", "--json"], cwd=notes).stdout)["due"]]
    check("not offered on the day it was skipped", "tasks" not in due())
    def backdate(stage, days, field="at", offers=None):
        import datetime as _dt
        d = json.loads(obj.read_text())
        then = (_dt.date.today() - _dt.timedelta(days=days)).isoformat()
        d["stages"][stage][field] = then + "T09:00:00"
        if offers is not None:
            d["stages"][stage]["offers"] = [(_dt.date.today() - _dt.timedelta(days=x)).isoformat() for x in offers]
        obj.write_text(json.dumps(d))
    backdate("tasks", 3)
    check("may be offered once the quiet period after a skip is over", "tasks" in due())
    run(ob + ["offered", "tasks"], cwd=notes)
    check("not again right after an offer", "tasks" not in due())
    backdate("tasks", 30, offers=[10])
    check("same stage stays quiet for a fortnight after an offer", "tasks" not in due())
    backdate("tasks", 30, offers=[15])
    check("eligible again after a fortnight", "tasks" in due())
    run(ob + ["later", "tasks", "--days", "10"], cwd=notes)
    check("'later' snoozes it", "tasks" not in due())
    backdate("tasks", 90, offers=[80, 50, 25])
    d = json.loads(obj.read_text()); d["stages"]["tasks"].pop("snoozed_until", None); obj.write_text(json.dumps(d))
    check("gives up after 3 offers", "tasks" not in due())
    run(ob + ["skip", "calendar_meetings"], cwd=notes)
    backdate("calendar_meetings", 10)
    run(ob + ["never", "calendar_meetings"], cwd=notes)
    check("'never' stops the offers", "calendar_meetings" not in due())
    run(ob + ["skip", "inbox_chat"], cwd=notes)
    backdate("inbox_chat", 10)
    backdate("tasks", 90, offers=[3])
    check("at most one offer of any stage per week", due() == [])
    backdate("tasks", 90, offers=[80, 50, 25])
    r = run(ob, cwd=notes)
    check("map lists skipped stages, still available", "SKIPPED, AND THERE WHEN YOU WANT THEM" in r.stdout and "Your task tracker" in r.stdout)
    check("map leaves out a 'never' stage from offers", "/onboard calendar_meetings" not in r.stdout)
    r = run(ob + ["done", "tasks"], cwd=notes)
    check("a skipped stage can still be done later", json.loads(obj.read_text())["stages"]["tasks"]["status"] == "done")

    print("\ncopy mode (systems without links)")
    win = tmp / "copyws"
    r = run([sys.executable, S / "setup.py", str(win)], env={"MORNING_NO_SYMLINK": "1"})
    check("engine copied, not linked", (win / "morning/engine/notify.py").is_file()
          and not (win / "morning/engine").is_symlink())
    r = run([sys.executable, S / "setup.py", str(win), "--refresh"])
    check("--refresh re-copies the engine", "refreshed from the package" in r.stdout, r.stdout[-200:])

    print("\nMac and Windows install path")
    qs = tmp / "qs-folder"
    r = run([sys.executable, S / "quickstart.py"], env={"MORNING_QS_CLIENT": "claude", "MORNING_QS_FOLDER": str(qs),
                                                       "HOME": str(tmp / "home-claude"), "USERPROFILE": str(tmp / "home-claude")})
    check("guided quickstart sets up a folder", r.returncode == 0 and (qs / "morning/config.yml").is_file(), (r.stdout + r.stderr)[-300:])
    check("quickstart ends with what to open next", "/onboard" in r.stdout)
    enc = {"PYTHONIOENCODING": "cp1252"}
    for cmd in (["morning/engine/onboard.py"], ["morning/engine/doctor.py"], ["morning/engine/onboard.py", "revisit"]):
        r = run([sys.executable, *cmd], cwd=qs, env=enc)
        check(f"Windows console code page: {' '.join(cmd)}", "UnicodeEncodeError" not in r.stderr, r.stderr[-200:])
    win = qs.parent / "win-sim"
    r = run([sys.executable, S / "setup.py", str(win)], env={"MORNING_NO_SYMLINK": "1", **enc})
    r = run([sys.executable, "morning/engine/doctor.py", "--home", str(tmp / "home-claude")], cwd=win, env=enc)
    check("a copied (Windows-style) workspace passes the doctor", r.returncode == 0, r.stdout[-300:])
    bat = (PKG / "Start here - Windows.bat").read_bytes()
    check("Windows launcher has Windows line endings", b"\r\n" in bat and b"py -3 scripts\\quickstart.py" in bat)
    cmdf = PKG / "Start here - Mac.command"
    check("Mac launcher is executable", os.access(cmdf, os.X_OK))
    r = run(["bash", "-n", str(cmdf)])
    check("Mac launcher syntax", r.returncode == 0)

    print("\nscheduled runners, with stand-in clients")
    if not zsh:
        print("  - skipped, zsh is not installed")
    stub = tmp / "stub"
    stub.mkdir()
    body = ('#!/bin/sh\nD=$(date +%Y-%m-%d)\nprintf "# Morning Brief\\n\\n## ── TOP OF YOUR LIST ──\\n\\ntest\\n" '
            '> morning/briefs/$D.md\nexit 0\n')
    for name in ("claude", "opencode", "codex"):
        (stub / name).write_text(body)
        (stub / name).chmod(0o755)
    for client, tpl in (("claude", "run-prep.template.sh"), ("opencode", "run-prep.opencode.template.sh"),
                        ("codex", "run-prep.codex.template.sh")) if zsh else ():
        ws = tmp / f"runner-{client}"
        run([sys.executable, S / "setup.py", str(ws), "--client", client])
        text = (S / tpl).read_text().replace("<PATH TO YOUR WORKSPACE>", str(ws))
        text = re.sub(r'^export PATH="', f'export PATH="{stub}:', text, count=1, flags=re.M)
        runner = ws / "morning/state/run-prep.sh"
        runner.write_text(text)
        r = run([zsh, str(runner)], cwd=ws, env={"HOME": str(tmp / f"home-{client}"), "MORNING_NOTIFY_CHANNEL": "file",
                                                "MORNING_NO_ALERT": "1", "MORNING_SKIP_NET_GATE": "1"}, timeout=600)
        log = (ws / "morning/state/runner.log").read_text() if (ws / "morning/state/runner.log").exists() else ""
        rec = next((ws / "morning/state/receipts").glob("*.json"), None)
        status = json.loads(rec.read_text()).get("status") if rec else None
        check(f"{client}: runner exits 0", r.returncode == 0, log[-300:])
        check(f"{client}: brief rendered and receipted", status == "rendered_not_sent", f"receipt status {status}")
        check(f"{client}: nothing written into the package", not (PKG / "morning").exists())

    print()
    if FAILS:
        print(f"✗ {len(FAILS)} check(s) failed: {', '.join(FAILS)}")
        print(f"  the rehearsal folder is kept for a look: {tmp}")
        return 1
    shutil.rmtree(tmp, ignore_errors=True)
    print("✓ every check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
