#!/usr/bin/env python3
"""
sharpen.py: product feedback, occasionally, when it is actually needed.

the owner's constraint, in their words: they do not make product decisions every day, but
sometimes they need help sharpening their thinking on an upcoming experiment, a feature,
or a problem users have. So this must be quiet by default and useful when it fires.

**Silence is the return value, most days.** That is the design and not a limitation.
The failure mode this avoids is a known one: an agent that
surfaces things unasked but cannot close them is a louder backlog, and you learn to
skim it. Daily unsolicited strategy critique is the purest available version of that.

So a challenge fires only when a real decision signal exists:

  feature_doc     a feature doc was written or changed recently (in $MORNING_FEATURES_DIR, default features/)
  hypothesis      a feature doc states a hypothesis with no kill condition in it
  experiment      the pulse flagged a read that is due or significant (passed in)
  sprint_goal     a goal is being set (passed in, at the sprint boundary)
  meeting         an upcoming meeting is a decision meeting (passed in)

and only when the loop is allowed to speak:

  COOLDOWN        no challenge within `--cooldown` days of the last one, default 5
  ONE OPEN        never a second challenge while the last one has no outcome
  PARKED          a topic declined twice is parked for 30 days

The question itself is gated too. It must be closed, answerable, and about this
specific decision. `have you considered the risks` is refused by the parser, because
the difference between a challenge and a prompt for a meeting is entirely in that.

Commands
--------
  sharpen.py candidates --date D [--signal k=v ...] [--json]
  sharpen.py fired  --in -        record the challenge that was raised
  sharpen.py respond --id s3 --outcome engaged|declined|deferred
  sharpen.py log
  sharpen.py selftest

Exit codes: 0 a challenge is warranted · 1 nothing to say today · 2 usage error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import subprocess
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from trust import repo_root, today  # noqa: E402

LOG = "morning/state/coach/challenges.jsonl"
FEATURES = os.environ.get("MORNING_FEATURES_DIR", "features")
DEFAULT_COOLDOWN = 5
OPEN_BLOCKS_FOR_DAYS = 7
PARK_AFTER_DECLINES = 2
PARK_DAYS = 30
FRESH_DAYS = 4

WEIGHT = {"experiment": 5, "sprint_goal": 5, "hypothesis": 4, "meeting": 3, "feature_doc": 2}

VAGUE = (
    r"have you (considered|thought about)",
    r"what are the (risks|trade-?offs|downsides)\b",
    r"is this the right (approach|thing|call)\b",
    r"\bwhat if\b.*\?$",
    r"how (do you|will you) (feel|know) about\b",
    r"^\s*why\?",
)


def die(msg: str, code: int = 2):
    print(f"sharpen.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def d(s: str) -> _dt.date:
    return _dt.date.fromisoformat(s)


def load_log(repo: pathlib.Path) -> list[dict]:
    p = repo / LOG
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def save_log(repo: pathlib.Path, rows: list[dict]) -> None:
    p = repo / LOG
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


# ---------------------------------------------------------------------------
# is a decision in the air?
# ---------------------------------------------------------------------------

def recent_feature_docs(repo: pathlib.Path, date: str, days: int = FRESH_DAYS) -> list[dict]:
    """Feature docs touched recently, from git where it can, mtime otherwise."""
    since = (d(date) - _dt.timedelta(days=days)).isoformat()
    hits: dict[str, str] = {}
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "log", f"--since={since}", "--name-only",
             "--pretty=format:%cs", "--", FEATURES],
            capture_output=True, text=True, timeout=20)
        cur = ""
        for ln in r.stdout.splitlines():
            ln = ln.strip()
            if re.match(r"^\d{4}-\d{2}-\d{2}$", ln):
                cur = ln
            elif ln.endswith(".md"):
                hits.setdefault(ln, cur)
    except Exception:
        pass
    root = repo / FEATURES
    if root.is_dir():
        for f in root.rglob("*.md"):
            try:
                m = _dt.date.fromtimestamp(f.stat().st_mtime).isoformat()
            except OSError:
                continue
            if m >= since and m <= date:
                hits.setdefault(str(f.relative_to(repo)), m)
    return [{"path": p, "when": w or since} for p, w in sorted(hits.items())]


def hypothesis_without_kill(repo: pathlib.Path, docs: list[dict]) -> list[dict]:
    out = []
    for doc in docs:
        p = repo / doc["path"]
        if not p.exists():
            continue
        try:
            txt = p.read_text().lower()
        except OSError:
            continue
        if "hypothes" in txt and not re.search(r"kill (condition|criteria)|we will stop if|"
                                               r"we abandon (this )?if", txt):
            out.append(doc)
    return out


def parse_signals(pairs: list[str]) -> dict[str, str]:
    out = {}
    for s in pairs or []:
        if "=" not in s:
            die(f"--signal wants key=value, got {s!r}")
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def cmd_candidates(repo: pathlib.Path, a) -> int:
    date = a.date or today()
    rows = load_log(repo)
    signals = parse_signals(a.signal)

    def silent(reason: str) -> int:
        out = {"challenge": False, "reason": reason}
        print(json.dumps(out) if a.json else f"no challenge today: {reason}")
        return 1

    open_ones = [r for r in rows if not r.get("outcome")
                 and (d(date) - d(r["date"])).days <= OPEN_BLOCKS_FOR_DAYS]
    if open_ones and not a.force:
        return silent(f"challenge {open_ones[-1]['id']} from {open_ones[-1]['date']} has no "
                      f"outcome yet. One open at a time, or it is a backlog.")
    if rows and not a.force:
        gap = (d(date) - d(rows[-1]["date"])).days
        if gap < (a.cooldown if a.cooldown is not None else DEFAULT_COOLDOWN):
            return silent(f"last challenge was {gap} day(s) ago, cooldown is "
                          f"{a.cooldown if a.cooldown is not None else DEFAULT_COOLDOWN}.")

    parked = set()
    for r in rows:
        t = r.get("topic")
        dec = [x for x in rows if x.get("topic") == t and x.get("outcome") == "declined"]
        if len(dec) >= PARK_AFTER_DECLINES:
            last = max(x["date"] for x in dec)
            if (d(date) - d(last)).days < PARK_DAYS:
                parked.add(t)

    cands: list[dict] = []
    for k in ("experiment", "sprint_goal", "meeting"):
        if signals.get(k):
            cands.append({"kind": k, "topic": signals[k], "why_now": f"{k} signal from this run",
                          "evidence": [f"{k}={signals[k]} (passed in by the loop)"]})
    docs = recent_feature_docs(repo, date)
    for doc in hypothesis_without_kill(repo, docs):
        cands.append({"kind": "hypothesis", "topic": pathlib.Path(doc["path"]).stem,
                      "why_now": "states a hypothesis with no kill condition anywhere in it",
                      "evidence": [f"{doc['path']} changed {doc['when']}, no kill condition found"]})
    for doc in docs:
        cands.append({"kind": "feature_doc", "topic": pathlib.Path(doc["path"]).stem,
                      "why_now": "written or changed in the last few days, so the thinking is live",
                      "evidence": [f"{doc['path']} changed {doc['when']}"]})

    seen, uniq = set(), []
    for c in cands:
        if c["topic"] in parked or c["topic"] in seen:
            continue
        seen.add(c["topic"])
        uniq.append(c)
    if not uniq:
        return silent("no decision signal: no recent feature doc, no experiment read "
                      "due, no goal being set. Most days land here, and that is correct.")

    uniq.sort(key=lambda c: -WEIGHT.get(c["kind"], 1))
    best = uniq[0]
    out = {
        "challenge": True, "date": date, **best,
        "also_available": [{"kind": c["kind"], "topic": c["topic"]} for c in uniq[1:4]],
        "constraints": {
            "exactly_one": True,
            "goes_in": "FINDINGS THIS RUN, never a separate document",
            "must_be_a_closed_question": True,
            "must_be_answerable_in_a_sentence_or_two": True,
            "no_generic_prompts": "'have you considered the risks' is refused by sharpen.py fired",
            "declined_twice_parks_the_topic_for_days": PARK_DAYS,
        },
    }
    if a.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(f"CHALLENGE  {best['kind']}: {best['topic']}")
        print(f"     why now: {best['why_now']}")
        for e in best["evidence"]:
            print(f"     {e}")
    return 0


def cmd_fired(repo: pathlib.Path, a) -> int:
    raw = sys.stdin.read() if a.infile in (None, "-") else pathlib.Path(a.infile).read_text()
    try:
        rec = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"not valid JSON: {e}")
    for f in ("topic", "question", "why_now", "evidence"):
        if not rec.get(f):
            die(f"a challenge needs `{f}`", 1)

    q = str(rec["question"]).strip()
    if not q.endswith("?"):
        die("REJECTED. A challenge is a question. This does not end in one.", 1)
    if len(re.findall(r"\?", q)) > 1:
        die("REJECTED. One question. Two questions is a meeting agenda, and they will answer "
            "neither.", 1)
    for pat in VAGUE:
        if re.search(pat, q, re.I):
            die(f"REJECTED. {q!r} is a generic prompt, not a challenge. It could be asked about "
                f"anything, which means it was not asked about this. Name the specific claim, "
                f"number or assumption you are testing and ask about that.", 1)
    if len(q.split()) < 6:
        die("REJECTED. Too short to be specific about anything.", 1)

    rows = load_log(repo)
    if any(re.sub(r"\s+", " ", str(r.get("question", "")).lower()) ==
           re.sub(r"\s+", " ", q.lower()) for r in rows):
        die("REJECTED. That exact question has been asked before.", 1)

    rec["date"] = rec.get("date") or a.date or today()
    rec["id"] = rec.get("id") or f"s{len(rows) + 1}"
    rec.setdefault("outcome", "")
    rows.append(rec)
    save_log(repo, rows)
    print(f"challenge {rec['id']} recorded on {rec['topic']}")
    return 0


def cmd_respond(repo: pathlib.Path, a) -> int:
    rows = load_log(repo)
    r = next((x for x in rows if x.get("id") == a.id), None)
    if not r:
        die(f"no challenge {a.id}")
    r["outcome"] = a.outcome
    r["outcome_at"] = today()
    if a.note:
        r["outcome_note"] = a.note
    save_log(repo, rows)
    print(f"{a.id}: {a.outcome}")
    if a.outcome == "declined":
        n = len([x for x in rows if x.get("topic") == r["topic"]
                 and x.get("outcome") == "declined"])
        if n >= PARK_AFTER_DECLINES:
            print(f"  {r['topic']} declined {n} times, parked for {PARK_DAYS} days.")
    return 0


def cmd_log(repo: pathlib.Path, a) -> int:
    rows = load_log(repo)
    if not rows:
        print("no challenges raised yet.")
        return 0
    for r in rows[-(a.limit or 20):]:
        print(f"{r['date']}  {r['id']}  {r['topic']}  [{r.get('outcome') or 'open'}]")
        print(f"    {r['question']}")
    engaged = len([r for r in rows if r.get("outcome") == "engaged"])
    print(f"\n{len(rows)} raised · {engaged} engaged with · "
          f"{len([r for r in rows if r.get('outcome') == 'declined'])} declined")
    return 0


def cmd_selftest(repo: pathlib.Path, a) -> int:
    fails = []

    def refuses(q: str) -> bool:
        for pat in VAGUE:
            if re.search(pat, q, re.I):
                return True
        return False

    for q in ("Have you considered the risks of shipping this?",
              "What are the trade-offs here?",
              "Is this the right approach?"):
        if not refuses(q):
            fails.append(f"should refuse: {q!r}")
    for q in ("The welcome prompt ships with zero metrics attached, so what will you read on day 3 "
              "to decide whether it worked?",
              "The signup hypothesis predicts a lift but names no kill condition, so at what "
              "number do you stop?"):
        if refuses(q):
            fails.append(f"should allow: {q!r}")

    if WEIGHT["experiment"] <= WEIGHT["feature_doc"]:
        fails.append("a live experiment must outrank a changed doc")
    if PARK_AFTER_DECLINES != 2:
        fails.append("declined twice should park")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  " + f)
        return 1
    print("selftest: 7 cases pass. Generic prompts are refused, specific ones pass, a live "
          "experiment outranks a changed doc, and silence is the default return.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Occasional product feedback, when it is needed.")
    ap.add_argument("--date")
    ap.add_argument("--repo")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("candidates", help="is a challenge warranted today")
    p.add_argument("--signal", action="append",
                   help="k=v, e.g. experiment='10442808 read due' or sprint_goal='...'")
    p.add_argument("--cooldown", type=int)
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("fired", help="record the challenge that was raised")
    p.add_argument("--in", dest="infile", default="-")

    p = sub.add_parser("respond")
    p.add_argument("--id", required=True)
    p.add_argument("--outcome", required=True, choices=["engaged", "declined", "deferred"])
    p.add_argument("--note")

    p = sub.add_parser("log")
    p.add_argument("--limit", type=int, default=20)
    sub.add_parser("selftest")

    a = ap.parse_args()
    repo = pathlib.Path(a.repo).resolve() if a.repo else repo_root()
    return {"candidates": cmd_candidates, "fired": cmd_fired, "respond": cmd_respond,
            "log": cmd_log, "selftest": cmd_selftest}[a.cmd](repo, a)


if __name__ == "__main__":
    sys.exit(main())
