#!/usr/bin/env python3
"""
coach.py: the daily coaching engine behind the morning loop.

What the owner asked for, in their words: coaching that reads their past decisions, actions
and goals; that helps them see the forest from the trees and the other way around;
that is stoic, so it focuses on what they can control and change; that assumes a
growth mindset, so it is about getting better every day rather than being graded;
that may hold a long-term development plan they are not briefed on and steer toward it
through the daily loop; and that they never has to call.

Nothing here writes the coaching. A model does that. This owns the parts that must
not drift, because a coach that drifts becomes either a nag or a horoscope:

  SELECTION   which development thread is due today, by priority and staleness,
              so the plan advances instead of the loop repeating its favourite point
  ZOOM        forest or trees, decided from measured spread across the recent plan
              files rather than from a mood. Deep on one thing -> widen. Scattered
              across a dozen -> narrow.
  SPACING     one nudge a day, never the same thread two days running, never the
              same observation twice, and a nudge declined twice is parked for a
              month. This is the carry ladder applied to coaching, and it is the
              only thing standing between daily coaching and daily noise.
  STOIC FRAME enforced structurally: a nudge without `in_your_control`,
              `not_in_your_control` and `today_action` is REJECTED. A model told to
              be stoic forgets by Thursday; a schema does not.
  GROWTH      movement per thread over weeks, from recorded outcomes, so the
              question is what changed rather than how you rate.

State, all readable, none hidden from them:

    coach/plan.md            the long-term development plan
    coach/observations.jsonl dated observations with their evidence
    coach/nudges.jsonl       what was surfaced, when, and what came of it

The plan is not recited in the daily brief, which is what "a plan I am not aware of"
means in practice. It is a file in their own repo and they can read it whenever they want.
Steering them toward a plan is coaching. Hiding it from them if they ask would be
something else, so `coach.py plan` prints it in full.

Commands
--------
  coach.py due     --date D [--json]   is coaching due, on what, at which zoom
  coach.py observe --in -              record an observation with its evidence
  coach.py nudge   --in -              record what was surfaced (stoic fields required)
  coach.py respond --id n7 --outcome acted|declined|deferred
  coach.py review  [--since D]         movement per thread + the draft-versus-posted pairs
  coach.py plan | threads | log
  coach.py selftest

Exit codes: 0 fine · 1 nothing due, or a rejected nudge · 2 usage error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import re
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from trust import repo_root, today  # noqa: E402

COACH_DIR = "morning/state/coach"
PLAN_FILE = "plan.md"
OBS_FILE = "observations.jsonl"
NUDGE_FILE = "nudges.jsonl"
PLANS_GLOB = "morning/briefs/*.md"

MIN_GAP_DAYS_SAME_THREAD = 2      # never the same thread two mornings running
PARK_AFTER_DECLINES = 2           # declined twice, parked
PARK_DAYS = 30
LOOKBACK_PLANS = 5                # how many recent morning plans the zoom reads
WIDE_CONCENTRATION = 0.40         # one ticket owns this much of recent attention -> widen
NARROW_SPREAD = 12                # this many distinct tickets with no anchor -> narrow

REQUIRED_NUDGE_FIELDS = ("thread", "observation", "in_your_control",
                         "not_in_your_control", "today_action")


def die(msg: str, code: int = 2):
    print(f"coach.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def d(s: str) -> _dt.date:
    return _dt.date.fromisoformat(s)


def days_between(a: str, b: str) -> int:
    return (d(a) - d(b)).days


class Store:
    def __init__(self, repo: pathlib.Path):
        self.repo = repo
        self.dir = repo / COACH_DIR

    def _read(self, name: str) -> list[dict]:
        p = self.dir / name
        if not p.exists():
            return []
        out = []
        for ln in p.read_text().splitlines():
            if ln.strip():
                out.append(json.loads(ln))
        return out

    def _append(self, name: str, rec: dict) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with (self.dir / name).open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _rewrite(self, name: str, rows: list[dict]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    def observations(self) -> list[dict]:
        return self._read(OBS_FILE)

    def nudges(self) -> list[dict]:
        return self._read(NUDGE_FILE)

    def plan_text(self) -> str:
        p = self.dir / PLAN_FILE
        return p.read_text() if p.exists() else ""

    def threads(self) -> list[dict]:
        """Parsed from plan.md. One `## {id} · {title}` block per thread, with a
        `priority:` and `horizon:` line. The plan is the source of truth; this
        only reads it, so editing the plan changes the coaching."""
        out = []
        cur = None
        for ln in self.plan_text().splitlines():
            m = re.match(r"^##\s+`([a-z0-9-]+)`\s*[:·]\s*(.+?)\s*$", ln)
            if m:
                cur = {"id": m.group(1), "title": m.group(2), "priority": 3,
                       "horizon": "", "parked_until": ""}
                out.append(cur)
                continue
            if cur is None:
                continue
            m = re.match(r"^\s*-\s*\*\*priority:\*\*\s*(\d+)", ln)
            if m:
                cur["priority"] = int(m.group(1))
            m = re.match(r"^\s*-\s*\*\*horizon:\*\*\s*(.+?)\s*$", ln)
            if m:
                cur["horizon"] = m.group(1)
            m = re.match(r"^\s*-\s*\*\*parked until:\*\*\s*(\S+)", ln)
            if m:
                cur["parked_until"] = m.group(1)
        return out


# ---------------------------------------------------------------------------
# zoom: forest or trees, measured
# ---------------------------------------------------------------------------

def attention_spread(repo: pathlib.Path, date: str, lookback: int = LOOKBACK_PLANS) -> dict:
    """Where their attention has actually been, read from the recent morning plans.

    Not a mood and not a self-report: the distinct ticket keys the last few plans
    mention, and how concentrated they are. Deep on one thing is a different problem
    from spread across a dozen, and they need opposite coaching.
    """
    files = sorted((repo / "morning/briefs").glob("morning-plan-*.md"))
    files = [f for f in files if f.stem.replace("morning-plan-", "") <= date][-lookback:]
    counts: dict[str, int] = {}
    for f in files:
        for k in set(re.findall(r"\b[A-Z][A-Z0-9]{1,9}-\d{1,6}\b", f.read_text())):
            counts[k] = counts.get(k, 0) + 1
    total = sum(counts.values())
    top_key, top_n = (max(counts.items(), key=lambda kv: kv[1]) if counts else ("", 0))
    return {"plans_read": len(files), "spread": len(counts), "total_mentions": total,
            "top_key": top_key, "top_share": round(top_n / total, 3) if total else 0.0}


def decide_zoom(spread: dict, last_zoom: str | None) -> tuple[str, str]:
    if spread["spread"] and spread["top_share"] >= WIDE_CONCENTRATION:
        return "wide", (f"{spread['top_key']} is {int(spread['top_share']*100)}% of what the last "
                        f"{spread['plans_read']} plans talked about. That is deep, and deep is where "
                        f"the wider question stops getting asked.")
    if spread["spread"] >= NARROW_SPREAD and spread["top_share"] < 0.20:
        return "narrow", (f"{spread['spread']} distinct tickets across the last "
                          f"{spread['plans_read']} plans and nothing above "
                          f"{int(spread['top_share']*100)}%. That is spread thin, and spread thin is "
                          f"where nothing finishes.")
    flip = {"wide": "narrow", "narrow": "wide"}
    if last_zoom in flip:
        return flip[last_zoom], "no strong signal either way, so alternating from yesterday."
    return "narrow", "no strong signal either way, and narrow is the cheaper default."


# ---------------------------------------------------------------------------
# selection + spacing
# ---------------------------------------------------------------------------

def thread_state(st: Store, threads: list[dict], date: str) -> list[dict]:
    nudges = st.nudges()
    obs = st.observations()
    out = []
    for t in threads:
        mine = [n for n in nudges if n.get("thread") == t["id"]]
        declines = [n for n in mine if n.get("outcome") == "declined"]
        last = max((n["date"] for n in mine), default="")
        acted = [n for n in mine if n.get("outcome") == "acted"]
        open_obs = [o for o in obs if o.get("thread") == t["id"] and not o.get("closed")]
        parked_until = t.get("parked_until") or ""
        if len(declines) >= PARK_AFTER_DECLINES:
            last_decline = max(n["date"] for n in declines)
            auto_park = (d(last_decline) + _dt.timedelta(days=PARK_DAYS)).isoformat()
            parked_until = max(parked_until, auto_park)
        out.append({**t, "nudges": len(mine), "acted": len(acted),
                    "declined": len(declines), "last_nudge": last,
                    "open_observations": len(open_obs), "parked_until": parked_until,
                    "days_since": days_between(date, last) if last else 999})
    return out


def pick_thread(states: list[dict], date: str) -> tuple[dict | None, str]:
    eligible = []
    for t in states:
        if t["parked_until"] and t["parked_until"] > date:
            continue
        if t["days_since"] < MIN_GAP_DAYS_SAME_THREAD:
            continue
        eligible.append(t)
    if not eligible:
        return None, "every thread is either parked or was raised too recently."
    # priority first (1 is highest), then staleness, then open observations.
    eligible.sort(key=lambda t: (t["priority"], -t["days_since"], -t["open_observations"]))
    t = eligible[0]
    return t, (f"priority {t['priority']}, last raised "
               + (f"{t['days_since']} days ago" if t["last_nudge"] else "never")
               + f", {t['open_observations']} open observation(s).")


def cmd_due(repo: pathlib.Path, a) -> int:
    st = Store(repo)
    date = a.date or today()
    threads = st.threads()
    if not threads:
        out = {"nudge": False, "reason": "no coaching plan yet: "
               f"write {COACH_DIR}/{PLAN_FILE} with one `## \\`id\\` · title` block per thread."}
        print(json.dumps(out) if a.json else out["reason"])
        return 1

    nudges = st.nudges()
    if any(n["date"] == date for n in nudges) and not a.force:
        out = {"nudge": False, "reason": "already coached today. One a day is the whole design."}
        print(json.dumps(out) if a.json else out["reason"])
        return 1

    states = thread_state(st, threads, date)
    thread, why = pick_thread(states, date)
    if thread is None:
        out = {"nudge": False, "reason": why}
        print(json.dumps(out) if a.json else out["reason"])
        return 1

    spread = attention_spread(repo, date)
    last_zoom = nudges[-1].get("zoom") if nudges else None
    zoom, zoom_reason = decide_zoom(spread, last_zoom)
    obs = [o for o in st.observations()
           if o.get("thread") == thread["id"] and not o.get("closed")]
    recent = [n for n in nudges if n.get("thread") == thread["id"]][-3:]

    out = {
        "nudge": True, "date": date,
        "thread": {k: thread[k] for k in ("id", "title", "priority", "horizon")},
        "selection_reason": why,
        "zoom": zoom, "zoom_reason": zoom_reason, "attention": spread,
        "open_observations": obs,
        "recent_nudges_on_this_thread": [
            {k: n.get(k) for k in ("date", "observation", "today_action", "outcome")}
            for n in recent],
        "constraints": {
            "one_nudge_per_day": True,
            "must_name_what_is_in_his_control": True,
            "must_end_in_one_action_he_can_take_today": True,
            "never_repeat_an_observation_verbatim": True,
            "declined_twice_parks_the_thread_for_days": PARK_DAYS,
        },
    }
    if a.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"DUE  thread `{thread['id']}` ({thread['title']})  zoom: {zoom}")
        print(f"     {why}")
        print(f"     {zoom_reason}")
        if obs:
            print(f"     {len(obs)} open observation(s) on this thread")
    return 0


# ---------------------------------------------------------------------------
# recording
# ---------------------------------------------------------------------------

def read_in(arg: str | None) -> dict:
    raw = sys.stdin.read() if arg in (None, "-") else pathlib.Path(arg).read_text()
    if not raw.strip():
        die("empty input")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"input is not valid JSON: {e}")


def cmd_observe(repo: pathlib.Path, a) -> int:
    st = Store(repo)
    rec = read_in(a.infile)
    for f in ("thread", "what", "evidence"):
        if not str(rec.get(f) or "").strip():
            die(f"an observation needs `{f}`. Evidence especially: an observation without "
                f"something checkable is an opinion, and they will spot the difference.")
    ids = {t["id"] for t in st.threads()}
    if ids and rec["thread"] not in ids:
        die(f"unknown thread {rec['thread']!r}. Known: {', '.join(sorted(ids))}")
    rec.setdefault("date", a.date or today())
    rec.setdefault("id", f"o{len(st.observations()) + 1}")
    rec.setdefault("closed", False)
    st._append(OBS_FILE, rec)
    print(f"observation {rec['id']} recorded on `{rec['thread']}`")
    return 0


def cmd_nudge(repo: pathlib.Path, a) -> int:
    st = Store(repo)
    rec = read_in(a.infile)
    missing = [f for f in REQUIRED_NUDGE_FIELDS if not str(rec.get(f) or "").strip()]
    if missing:
        die("REJECTED. A coaching nudge must carry " + ", ".join(f"`{m}`" for m in missing)
            + ".\nThe stoic frame is the point: name the part of this they controls, name the part "
              "they do not so they can stop paying rent on it, and end in one thing they can do today. "
              "A nudge without those three is an observation, and observations go to `observe`.", 1)

    ids = {t["id"] for t in st.threads()}
    if ids and rec["thread"] not in ids:
        die(f"unknown thread {rec['thread']!r}. Known: {', '.join(sorted(ids))}")

    prior = st.nudges()
    norm = re.sub(r"\s+", " ", rec["observation"].strip().lower())
    for n in prior:
        if re.sub(r"\s+", " ", str(n.get("observation", "")).strip().lower()) == norm:
            die(f"REJECTED. This exact observation was already made on {n['date']} "
                f"({n.get('id')}). Repeating it word for word is how coaching becomes wallpaper. "
                f"Either escalate it (say what has not changed since, and raise the ask) or park "
                f"the thread.", 1)

    date = rec.get("date") or a.date or today()
    if any(n["date"] == date for n in prior) and not a.force:
        die("REJECTED. A nudge is already recorded for today. One a day.", 1)

    rec["date"] = date
    rec.setdefault("id", f"n{len(prior) + 1}")
    rec.setdefault("zoom", a.zoom or "")
    rec.setdefault("outcome", "")
    rec.setdefault("closes_observations", [])
    st._append(NUDGE_FILE, rec)

    if rec["closes_observations"]:
        obs = st.observations()
        for o in obs:
            if o.get("id") in rec["closes_observations"]:
                o["closed"] = True
        st._rewrite(OBS_FILE, obs)
    print(f"nudge {rec['id']} recorded on `{rec['thread']}` ({rec['zoom'] or 'zoom unset'})")
    return 0


def cmd_respond(repo: pathlib.Path, a) -> int:
    st = Store(repo)
    rows = st.nudges()
    n = next((x for x in rows if x.get("id") == a.id), None)
    if not n:
        die(f"no nudge {a.id}")
    n["outcome"] = a.outcome
    if a.note:
        n["outcome_note"] = a.note
    n["outcome_at"] = today()
    st._rewrite(NUDGE_FILE, rows)
    print(f"{a.id}: {a.outcome}")
    if a.outcome == "declined":
        dec = len([x for x in rows if x.get("thread") == n["thread"]
                   and x.get("outcome") == "declined"])
        if dec >= PARK_AFTER_DECLINES:
            print(f"  `{n['thread']}` has been declined {dec} times and is now parked for "
                  f"{PARK_DAYS} days. Declining twice is an answer, and the coach takes it.")
    return 0


def cmd_review(repo: pathlib.Path, a) -> int:
    """Movement per thread, plus the draft-versus-posted pairs worth reading.

    The pairs are the strongest coaching signal available: every edit they make to a
    draft before sending it is their judgment applied to a concrete artifact. Nothing
    could compute them until the outbound ledger existed.
    """
    st = Store(repo)
    since = a.since or (d(today()) - _dt.timedelta(days=7)).isoformat()
    nudges = [n for n in st.nudges() if n["date"] >= since]
    obs = [o for o in st.observations() if o.get("date", "") >= since]

    print(f"COACH REVIEW since {since}")
    print()
    for t in st.threads():
        mine = [n for n in nudges if n.get("thread") == t["id"]]
        acted = [n for n in mine if n.get("outcome") == "acted"]
        declined = [n for n in mine if n.get("outcome") == "declined"]
        openn = [n for n in mine if not n.get("outcome")]
        print(f"`{t['id']}` {t['title']}")
        print(f"    raised {len(mine)} · acted {len(acted)} · declined {len(declined)} "
              f"· awaiting an outcome {len(openn)}")
        for n in acted:
            print(f"    + {n['date']}: {n.get('today_action','')}")
        if openn:
            print(f"    ? {len(openn)} nudge(s) with no outcome recorded. An unanswered nudge "
                  f"is not a neutral result, it is the coaching equivalent of a carried item.")
    print()
    print(f"observations recorded in the window: {len(obs)}")
    print()

    ledger = repo / "morning/state/outbound-ledger.jsonl"
    pairs = []
    if ledger.exists():
        for ln in ledger.read_text().splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            if r["date"] >= since and r.get("draft"):
                pairs.append(r)
    print(f"DRAFT VERSUS POSTED: {len(pairs)} pair(s) in the window")
    if not pairs:
        print("    Nothing to compare. Record sends with /shipped, including the ones you make")
        print("    by hand. Every edit you make before sending is your judgment on a concrete")
        print("    artifact, and it is the highest-quality coaching signal available. It is also")
        print("    what the drafters need in order to get better, so one pass produces both.")
    for r in pairs:
        print(f"    {r['date']} {r['job']} -> {r['destination']}")
        print(f"        draft: {r['draft']}   verified-at-send: {r['verified_at_send']}")
    return 0


def cmd_plan(repo: pathlib.Path, a) -> int:
    st = Store(repo)
    txt = st.plan_text()
    if not txt:
        print(f"no plan yet. Write {COACH_DIR}/{PLAN_FILE}.")
        return 1
    print(txt)
    return 0


def cmd_threads(repo: pathlib.Path, a) -> int:
    st = Store(repo)
    date = a.date or today()
    states = thread_state(st, st.threads(), date)
    if not states:
        print("no threads: the plan is empty.")
        return 1
    for t in sorted(states, key=lambda x: x["priority"]):
        park = f" · PARKED until {t['parked_until']}" if t["parked_until"] > date else ""
        print(f"p{t['priority']} `{t['id']}` {t['title']}{park}")
        print(f"     raised {t['nudges']} · acted {t['acted']} · declined {t['declined']} "
              f"· last {t['last_nudge'] or 'never'} · open observations {t['open_observations']}")
    return 0


def cmd_log(repo: pathlib.Path, a) -> int:
    st = Store(repo)
    for n in st.nudges()[-(a.limit or 20):]:
        print(f"{n['date']}  {n.get('id')}  `{n.get('thread')}`  {n.get('zoom','')}  "
              f"[{n.get('outcome') or 'no outcome yet'}]")
        print(f"    {n.get('observation','')}")
        print(f"    control: {n.get('in_your_control','')}")
        print(f"    today:   {n.get('today_action','')}")
    return 0


def cmd_selftest(repo: pathlib.Path, a) -> int:
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append(f"{name}: got {got!r}, wanted {want!r}")

    # zoom is measured, not felt
    deep = {"spread": 6, "top_share": 0.55, "top_key": "PROJ-14058", "plans_read": 5}
    check("deep on one ticket widens", decide_zoom(deep, None)[0], "wide")
    thin = {"spread": 15, "top_share": 0.09, "top_key": "PROJ-1", "plans_read": 5}
    check("spread thin narrows", decide_zoom(thin, None)[0], "narrow")
    mid = {"spread": 7, "top_share": 0.25, "top_key": "PROJ-1", "plans_read": 5}
    check("no signal alternates", decide_zoom(mid, "wide")[0], "narrow")
    check("no signal alternates back", decide_zoom(mid, "narrow")[0], "wide")

    # spacing
    base = {"id": "x", "title": "t", "priority": 1, "horizon": "", "parked_until": "",
            "nudges": 1, "acted": 0, "declined": 0, "last_nudge": "2026-08-27",
            "open_observations": 0}
    t, _ = pick_thread([dict(base, days_since=1)], "2026-08-28")
    check("same thread two days running is refused", t, None)
    t, _ = pick_thread([dict(base, days_since=3)], "2026-08-28")
    check("same thread after the gap is allowed", t["id"], "x")
    t, _ = pick_thread([dict(base, days_since=9, parked_until="2026-09-30")], "2026-08-28")
    check("a parked thread is skipped", t, None)

    # priority wins, then staleness
    a1 = dict(base, id="a", priority=1, days_since=3)
    b1 = dict(base, id="b", priority=2, days_since=40)
    check("priority outranks staleness", pick_thread([b1, a1], "2026-08-28")[0]["id"], "a")
    a2 = dict(base, id="a", priority=2, days_since=3)
    check("staleness breaks a priority tie",
          pick_thread([a2, dict(base, id='b', priority=2, days_since=40)],
                      "2026-08-28")[0]["id"], "b")

    check("stoic fields are mandatory", REQUIRED_NUDGE_FIELDS,
          ("thread", "observation", "in_your_control", "not_in_your_control", "today_action"))

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  " + f)
        return 1
    print("selftest: 10 cases pass. Zoom is measured from the recent plans, the same thread "
          "cannot land two mornings running, a thread declined twice parks itself, and a nudge "
          "without the stoic frame is rejected rather than softened.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="The daily coaching engine.")
    ap.add_argument("--date")
    ap.add_argument("--repo")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("due", help="is coaching due, on what, at which zoom")
    p.add_argument("--json", action="store_true")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("observe", help="record an observation with its evidence")
    p.add_argument("--in", dest="infile", default="-")

    p = sub.add_parser("nudge", help="record what was surfaced")
    p.add_argument("--in", dest="infile", default="-")
    p.add_argument("--zoom", choices=["wide", "narrow"])
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("respond", help="what came of a nudge")
    p.add_argument("--id", required=True)
    p.add_argument("--outcome", required=True, choices=["acted", "declined", "deferred"])
    p.add_argument("--note")

    p = sub.add_parser("review", help="movement per thread + draft-versus-posted pairs")
    p.add_argument("--since")

    sub.add_parser("plan")
    sub.add_parser("threads")
    p = sub.add_parser("log")
    p.add_argument("--limit", type=int, default=20)
    sub.add_parser("selftest")

    a = ap.parse_args()
    repo = pathlib.Path(a.repo).resolve() if a.repo else repo_root()
    return {"due": cmd_due, "observe": cmd_observe, "nudge": cmd_nudge,
            "respond": cmd_respond, "review": cmd_review, "plan": cmd_plan,
            "threads": cmd_threads, "log": cmd_log, "selftest": cmd_selftest}[a.cmd](repo, a)


if __name__ == "__main__":
    sys.exit(main())
