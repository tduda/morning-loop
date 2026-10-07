#!/usr/bin/env python3
"""onboard.py: the onboarding map. Which stages are done, what each one gave you,
and what the next one costs and unlocks.

The point of the map is the trade: every stage says how many minutes it takes and
what you get from it, so you can decide what is worth your time before you spend
it. /onboard drives the stages; this script only keeps score.

    python3 morning/engine/onboard.py              # the map
    python3 morning/engine/onboard.py show tasks   # one stage in full
    python3 morning/engine/onboard.py done tasks   # mark a stage done (after its test read passed)
    python3 morning/engine/onboard.py skip metrics # skip an optional stage
    python3 morning/engine/onboard.py reset tasks  # back to pending
    python3 morning/engine/onboard.py revisit      # skipped stages that MAY be offered, if today's work calls for one
    python3 morning/engine/onboard.py offered tasks   # the brief offered it today
    python3 morning/engine/onboard.py later tasks --days 14   # not now, ask again later
    python3 morning/engine/onboard.py never tasks  # stop offering it
    python3 morning/engine/onboard.py --json       # for the agent

Skipped is not forgotten, and it is never nagged about. There is no schedule: a
skipped stage is offered again only when today's work shows it would help the task
at hand (each stage names that signal in `revisit_when`), framed around that task.
This script only says which stages MAY be offered; the caller decides whether the
signal is there. The quiet periods below keep even well-timed offers rare.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

QUIET_AFTER_SKIP_DAYS = 2   # never re-offer right after someone said no
STAGE_COOLDOWN_DAYS = 14    # the same stage at most once a fortnight, however relevant
GLOBAL_COOLDOWN_DAYS = 7    # at most one onboarding offer of any kind per week
MAX_OFFERS = 3              # and never more than three times per stage, unless the user asks
SNOOZE_DAYS = 21            # what "later" means when no number is given

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE.parent
STAGES_DIR = PKG / "stages"


# --------------------------------------------------------------------------- stages
def parse_stage(path: pathlib.Path) -> dict:
    """Frontmatter (flat keys, plus `key: |` blocks) and the body. No YAML library needed."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise SystemExit(f"onboard: {path.name} has no frontmatter")
    meta: dict = {}
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        k, _, v = lines[i].partition(":")
        v = v.strip()
        if v == "|":
            block = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or not lines[i].strip()):
                block.append(lines[i][2:])
                i += 1
            meta[k.strip()] = "\n".join(block).rstrip()
            continue
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        meta[k.strip()] = {"true": True, "false": False}.get(v, int(v) if v.isdigit() else v)
        i += 1
    meta["body"] = m.group(2).strip()
    meta["file"] = path.name
    return meta


def stages() -> list[dict]:
    return sorted((parse_stage(p) for p in STAGES_DIR.glob("*.md")), key=lambda s: s["n"])


# --------------------------------------------------------------------------- state
def workspace() -> pathlib.Path | None:
    cwd = pathlib.Path.cwd()
    return next((p for p in [cwd, *cwd.parents] if (p / "morning" / "state").is_dir()), None)


def state_path(ws: pathlib.Path) -> pathlib.Path:
    return ws / "morning" / "state" / "onboarding.json"


def load(ws: pathlib.Path) -> dict:
    p = state_path(ws)
    if p.is_file():
        return json.loads(p.read_text())
    return {"started": dt.date.today().isoformat(), "stages": {}}


def save(ws: pathlib.Path, st: dict) -> None:
    state_path(ws).write_text(json.dumps(st, indent=2) + "\n")


# --------------------------------------------------------------------------- revisit
def revisit_due(all_stages: list[dict], st: dict, today: dt.date | None = None) -> list[dict]:
    """Skipped stages that MAY be offered today, if today's work gives a reason.
    Empty during any quiet period. Never a reason to offer on its own."""
    today = today or dt.date.today()
    recs = st["stages"]
    last_any = max((dt.date.fromisoformat(o) for r in recs.values() for o in r.get("offers", [])), default=None)
    if last_any and (today - last_any).days < GLOBAL_COOLDOWN_DAYS:
        return []
    out = []
    for s in all_stages:
        rec = recs.get(s["id"], {})
        if rec.get("status") != "skipped" or rec.get("never"):
            continue
        offers = rec.get("offers", [])
        if len(offers) >= MAX_OFFERS:
            continue
        snooze = rec.get("snoozed_until")
        if snooze and dt.date.fromisoformat(snooze) > today:
            continue
        skipped = dt.date.fromisoformat(rec.get("at", today.isoformat())[:10])
        if (today - skipped).days < QUIET_AFTER_SKIP_DAYS:
            continue
        if offers and (today - dt.date.fromisoformat(offers[-1])).days < STAGE_COOLDOWN_DAYS:
            continue
        out.append({"id": s["id"], "n": s["n"], "title": s["title"], "minutes": s["minutes"],
                    "unlocks": s["unlocks"], "revisit_when": s.get("revisit_when", ""),
                    "skipped_on": skipped.isoformat(), "times_offered": len(offers),
                    "offers_left": MAX_OFFERS - len(offers)})
    return sorted(out, key=lambda d: d["skipped_on"])


# --------------------------------------------------------------------------- render
MARK = {"done": "✓", "skipped": "·", "pending": "○", "next": "→"}


def statuses(all_stages: list[dict], st: dict) -> list[tuple[dict, str]]:
    out, nxt = [], None
    for s in all_stages:
        status = st["stages"].get(s["id"], {}).get("status", "pending")
        if status == "pending" and nxt is None:
            nxt, status = s["id"], "next"
        out.append((s, status))
    return out


def render_map(rows: list[tuple[dict, str]], st: dict) -> str:
    done = [s for s, k in rows if k == "done"]
    left = [s for s, k in rows if k in ("pending", "next")]
    nxt = next((s for s, k in rows if k == "next"), None)
    L = ["", "MORNING LOOP · ONBOARDING", ""]
    for s, k in rows:
        rec = st["stages"].get(s["id"], {})
        note = ""
        if k == "skipped":
            note = "  (skipped" + (", won't ask again" if rec.get("never") else
                                   f", offered {len(rec.get('offers', []))} time(s) since") + ")"
        L.append(f"  {MARK[k]} {s['n']}  {s['title']:<28} {str(s['minutes']) + ' min':>7}   {s['unlocks']}{note}")
    L.append("")
    if done:
        L.append("WHAT YOU HAVE NOW")
        L += [f"  · {s['unlocks']}" for s in done if s["id"] != "install"] or ["  · a working setup"]
        L.append("")
    skipped = [s for s, k in rows if k == "skipped" and not st["stages"].get(s["id"], {}).get("never")]
    if skipped:
        L.append("SKIPPED, AND THERE WHEN YOU WANT THEM")
        L += [f"  · stage {s['n']}, {s['title']} ({s['minutes']} min): {s['unlocks']}. /onboard {s['id']} to do it now" for s in skipped]
        L.append("  The brief only brings one up when it would help with something you're working on.")
        L.append("")
    if nxt:
        L.append(f"NEXT: stage {nxt['n']}, {nxt['title']} ({nxt['minutes']} minutes)")
        L.append(f"  You get: {nxt['unlocks']}")
        if nxt.get("brief_sample"):
            L.append("  It adds this to your brief:")
            L += ["    " + ln for ln in str(nxt["brief_sample"]).splitlines()]
        if nxt.get("recommended_after_days"):
            started = dt.date.fromisoformat(st.get("started", dt.date.today().isoformat()))
            days = (dt.date.today() - started).days
            if days < int(nxt["recommended_after_days"]):
                L.append(f"  Best after {nxt['recommended_after_days']} days of briefs (you're on day {days + 1}). It works now too.")
        mins = sum(int(s["minutes"]) for s in left)
        L.append("")
        L.append(f"Everything left: {len(left)} stage(s), about {mins} minutes. Stages 2, 3, 4, 6 and 7 can be skipped;")
        L.append("stage 5 can't: it's what makes the loop run itself.")
    else:
        L.append("All stages done or skipped. /onboard can revisit any of them.")
    return "\n".join(L)


# --------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="the onboarding map")
    ap.add_argument("cmd", nargs="?", default="map", choices=["map", "show", "done", "skip", "reset",
                                                             "revisit", "offered", "later", "never"])
    ap.add_argument("stage", nargs="?")
    ap.add_argument("--note", default="")
    ap.add_argument("--days", type=int, default=SNOOZE_DAYS)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    all_stages = stages()
    ids = {s["id"]: s for s in all_stages}
    ws = workspace()
    if ws is None and a.cmd != "show":
        print("onboard: no morning/ folder here or above. Run stage 0 first: python3 scripts/setup.py <folder>")
        return 2
    st = load(ws) if ws else {"stages": {}}

    if a.cmd in ("show", "done", "skip", "reset", "offered", "later", "never"):
        if a.stage not in ids:
            print(f"onboard: unknown stage {a.stage!r}. Stages: {', '.join(ids)}")
            return 2
    if a.cmd == "show":
        s = ids[a.stage]
        print(f"STAGE {s['n']} · {s['title']} · {s['minutes']} min\nUnlocks: {s['unlocks']}\n")
        print(s["body"])
        return 0
    if a.cmd == "skip" and not ids[a.stage].get("optional"):
        reason = ("it's what makes the loop run itself; without it nothing happens unless you type /morning. "
                  "It takes 5 minutes and you can do it right now, before any tools")
        if a.stage != "schedule":
            reason = "the brief needs it"
        print(f"onboard: stage {ids[a.stage]['n']} ({ids[a.stage]['title']}) can't be skipped: {reason}.")
        return 2
    if a.cmd == "revisit":
        due = revisit_due(all_stages, st)
        if a.json:
            print(json.dumps({"due": due}, indent=2))
        elif not due:
            print("No skipped stage may be offered today (none skipped, or a quiet period).")
        else:
            for d in due:
                print(f"stage {d['n']}, {d['title']} ({d['minutes']} min): {d['unlocks']}"
                      f"  [skipped {d['skipped_on']}, offered {d['times_offered']}x, {d['offers_left']} left]")
                if d["revisit_when"]:
                    print(f"  offer ONLY if today's work shows: {d['revisit_when']}")
        return 0
    if a.cmd in ("offered", "later", "never"):
        rec = st["stages"].setdefault(a.stage, {"status": "skipped", "at": dt.datetime.now().isoformat(timespec="seconds")})
        if rec.get("status") != "skipped":
            print(f"onboard: stage {a.stage} isn't skipped (it's {rec.get('status', 'pending')}); nothing to do.")
            return 0
        today = dt.date.today()
        if a.cmd == "offered":
            if today.isoformat() not in rec.setdefault("offers", []):
                rec["offers"].append(today.isoformat())
        elif a.cmd == "later":
            rec["snoozed_until"] = (today + dt.timedelta(days=a.days)).isoformat()
        else:
            rec["never"] = True
        save(ws, st)
        print({"offered": f"recorded: stage {a.stage} offered today",
               "later": f"ok: stage {a.stage} will be offered again on {rec.get('snoozed_until')}",
               "never": f"ok: stage {a.stage} won't be offered again. /onboard {a.stage} still works any time"}[a.cmd])
        return 0
    if a.cmd in ("done", "skip", "reset"):
        if a.cmd == "reset":
            st["stages"].pop(a.stage, None)
        else:
            st["stages"][a.stage] = {"status": "done" if a.cmd == "done" else "skipped",
                                     "at": dt.datetime.now().isoformat(timespec="seconds"), "note": a.note}
            # a stage done later (after being skipped) keeps its history of offers

        save(ws, st)

    rows = statuses(all_stages, st)
    if a.json:
        print(json.dumps({"workspace": str(ws), "stages": [
            {"id": s["id"], "n": s["n"], "title": s["title"], "minutes": s["minutes"],
             "status": k, "unlocks": s["unlocks"], "optional": bool(s.get("optional"))} for s, k in rows],
            "revisit_due": revisit_due(all_stages, st)}, indent=2))
        return 0
    print(render_map(rows, st))
    return 0


if __name__ == "__main__":
    sys.exit(main())
