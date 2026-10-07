#!/usr/bin/env python3
"""
asks.py: the ASK surface, answered in a file rather than through a command.

Why this exists
---------------
Between 2026-08-28 and 2026-09-24 the loop asked its owner **9 things** (7 coaching
nudges, 2 product challenges) and recorded **0 answers**. The 2026-09-07
autonomy assessment established the cause, and it is not unwillingness: on the
two days with recorded engagement they made 10 ticket decisions and 2 hand sends.
They act. What they never do is run a second command afterwards to record it.

The same cause sits under the carry ladder. `testDirection` reached `carried 3x`
and the milestone page `carried 8x`. They carried because they went unanswered,
and they went unanswered because answering cost a trip to a terminal.

So: **no command to answer.** They type under `**Answer:**` in a file they already
has open at the gate, and the next run parses it. An answered ask becomes a
provenance row, which is what finally fills the decision ledger.

The question format and its parser are adapted, with thanks, from a colleague's
`plan-drafting` package.
Their `parse_questions` is reproduced below in substance; the surrounding surface,
the carry ladder and the provenance handoff are this loop's.

Their rule on how many options to offer is adopted verbatim in spirit, and it is
better than the "1 to 3 candidate plans" this loop's own earlier design had:

    Options appear ONLY where the candidate answers change the outcome in
    materially different ways. Where there is one defensible answer there is no
    options list: state the answer you would take and make the question a
    confirmation. A clean run gets ZERO questions. The count is bounded by the
    blocker test, never by a quota.

Commands
--------
  asks.py --date D render --in <file>   write questions-{DATE}.md
  asks.py --date D parse [--json]       total / open / answered, from the file
  asks.py --date D carry --from PREV    bring unanswered asks forward, with counts
  asks.py selftest

Exit codes: 0 all answered or none asked · 1 something is still open · 2 usage.
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
from trust import Ctx, repo_root, today  # noqa: E402

_Q_HEADING = re.compile(r"^##\s+Q\d+\.", re.MULTILINE)
_ANSWER_MARK = "**Answer:**"
CARRY_LEAD_AT = 3        # at this many carries the count IS the finding, per carry.lead_with_count_at


def die(msg: str, code: int = 2):
    print(f"asks.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def path_for(ctx: Ctx) -> pathlib.Path:
    return ctx.review_dir / f"questions-{ctx.date}.md"


def parse_questions(text: str) -> tuple[int, int, list[dict]]:
    """(total, open_count, per-question detail).

    A question block runs from its `## Q<n>.` heading to the next one. Within a
    block the answer is everything between `**Answer:**` and the next `---` or
    the end of the block. The question is OPEN when that span has no
    non-whitespace content.

    A question with no Answer marker at all is malformed and counts as OPEN.
    Erring the other way would let a typo mark an ask as answered, and a
    silently-swallowed ask is the failure this file exists to end.

    Adapted from a colleague's plan-drafting `plan_state.parse_questions`.
    """
    starts = [m.start() for m in _Q_HEADING.finditer(text)]
    if not starts:
        return (0, 0, [])
    bounds = starts + [len(text)]
    out: list[dict] = []
    open_count = 0
    for i in range(len(starts)):
        block = text[bounds[i]:bounds[i + 1]]
        title = block.splitlines()[0].split(".", 1)[-1].strip()
        qid = block.splitlines()[0].strip().split(".")[0].replace("#", "").strip()
        idx = block.find(_ANSWER_MARK)
        if idx == -1:
            answer, is_open = "", True
        else:
            span = block[idx + len(_ANSWER_MARK):]
            cut = span.find("\n---")
            answer = (span if cut == -1 else span[:cut]).strip()
            is_open = not answer
        if is_open:
            open_count += 1
        out.append({"id": qid, "question": title, "answer": answer, "open": is_open,
                    "carried": _carried_of(block)})
    return (len(starts), open_count, out)


def _carried_of(block: str) -> int:
    m = re.search(r"carried\s+(\d+)x", block, re.I)
    return int(m.group(1)) if m else 0


def render(ctx: Ctx, asks: list[dict]) -> str:
    L = [f"# Open questions, {ctx.date}", ""]
    if not asks:
        L += ["**Nothing is blocked on you this run.**", "",
              "This file is written even when it is empty, on purpose. Its absence and "
              "\"no questions\" must not look identical: one means a quiet day, the other means "
              "the run never got this far.", ""]
        return "\n".join(L)

    L += [f"**{len(asks)} question(s).** Answer under each one, in this file. There is no command "
          f"to run and nothing to tick: type under `**Answer:**` and save. The next run reads it, "
          f"carries forward whatever is still blank, and records what you answered.", "",
          "A question is open until its Answer block has text in it.", "", "---", ""]
    for i, a in enumerate(asks, start=1):
        carried = a.get("carried", 0)
        tag = ""
        if carried >= CARRY_LEAD_AT:
            tag = f"  ·  **carried {carried}x, and the count is now the finding**"
        elif carried:
            tag = f"  ·  carried {carried}x"
        L += [f"## Q{i}. {a['question']}{tag}", ""]
        L += [f"**Why it matters:** {a.get('why_it_matters') or a.get('unblocks') or '_not stated_'}", ""]
        if a.get("ask"):
            L += [f"**Who can answer:** {a['ask']}", ""]
        opts = a.get("options") or []
        if opts:
            L += ["**Options:**", ""] + [f"- {o}" for o in opts] + [""]
        elif a.get("recommendation"):
            L += [f"**There is one defensible answer, so this is a confirmation rather than a menu.** "
                  f"Unless you say otherwise: {a['recommendation']}", ""]
        if a.get("evidence"):
            L += ["**Evidence:** " + " · ".join(str(e) for e in a["evidence"]), ""]
        L += ["**Answer:**", "", "---", ""]
    return "\n".join(L)


def cmd_render(ctx: Ctx, a) -> int:
    raw = sys.stdin.read() if a.infile in (None, "-") else pathlib.Path(a.infile).read_text()
    try:
        asks = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError as e:
        die(f"input is not valid JSON: {e}")
    if isinstance(asks, dict):
        asks = asks.get("asks") or []
    for q in asks:
        if not str(q.get("question") or "").strip():
            die("every ask needs a `question`")
        if not (q.get("why_it_matters") or q.get("unblocks")):
            die(f"ask {q.get('question','?')[:40]!r} has no `why_it_matters`. Name what changes "
                f"depending on the answer. If nothing changes, it is not a blocker and it does not "
                f"belong in front of them.")
        if len(q.get("options") or []) == 1:
            die(f"ask {q.get('question','?')[:40]!r} offers ONE option, which is a menu with one "
                f"item. Either name a second materially different option or drop the list and set "
                f"`recommendation`, making it a confirmation.")
    ctx.review_dir.mkdir(parents=True, exist_ok=True)
    path_for(ctx).write_text(render(ctx, asks))
    print(f"{len(asks)} question(s) -> {path_for(ctx).relative_to(ctx.repo)}")
    return 0


def cmd_parse(ctx: Ctx, a) -> int:
    p = path_for(ctx)
    if not p.exists():
        out = {"exists": False, "total": 0, "open": 0, "questions": [],
               "note": "no questions file for this date; absence is not the same as zero"}
        print(json.dumps(out) if a.json else out["note"])
        return 1
    total, open_count, detail = parse_questions(p.read_text())
    if a.json:
        print(json.dumps({"exists": True, "total": total, "open": open_count,
                          "answered": total - open_count, "questions": detail}, ensure_ascii=False))
    else:
        print(f"ASKS {ctx.date}: {total} asked · {total - open_count} answered · {open_count} open")
        for q in detail:
            mark = "open " if q["open"] else "ANSWERED"
            print(f"  [{mark}] {q['id']}. {q['question'][:70]}")
            if not q["open"]:
                print(f"           -> {q['answer'][:90]}")
    return 1 if open_count else 0


def cmd_carry(ctx: Ctx, a) -> int:
    """Bring yesterday's unanswered asks forward, with the carry count incremented."""
    if not a.prev:
        die("--from <YYYY-MM-DD> is required")
    prev = Ctx(a.prev, ctx.repo)
    pp = path_for(prev)
    if not pp.exists():
        print(f"no questions file for {a.prev}, nothing to carry")
        return 0
    _, _, detail = parse_questions(pp.read_text())
    carried = [{"question": q["question"], "carried": q["carried"] + 1}
               for q in detail if q["open"]]
    answered = [q for q in detail if not q["open"]]
    print(json.dumps({"carry": carried, "answered_last_run": answered}, ensure_ascii=False))
    if answered:
        print(f"# {len(answered)} answered since {a.prev}: record each as a provenance row "
              f"(tickets.py draft, kind=question, derived_from the ask)", file=sys.stderr)
    return 0


def cmd_selftest(ctx: Ctx, a) -> int:
    fails = []

    def check(n, got, want):
        if got != want:
            fails.append(f"{n}: got {got!r}, wanted {want!r}")

    q = """# Open questions

## Q1. Is the media-upload half still in scope?

**Why it matters:** the agenda gets written to a different priority.

**Options:**

- Keep it
- Cut it

**Answer:**

---
"""
    check("unanswered", parse_questions(q)[:2], (1, 1))
    check("answered", parse_questions(q.replace("**Answer:**", "**Answer:** Cut it."))[:2], (1, 0))
    check("whitespace is not an answer",
          parse_questions(q.replace("**Answer:**", "**Answer:**   \n  "))[:2], (1, 1))
    check("no questions", parse_questions("# Open questions\n\nNone.\n")[:2], (0, 0))
    check("missing Answer marker counts as open",
          parse_questions("## Q1. A thing?\n\n**Why it matters:** x\n")[:2], (1, 1))
    two = q + q.replace("Q1.", "Q2.").replace("**Answer:**", "**Answer:** yes")
    check("two questions, one answered", parse_questions(two)[:2], (2, 1))
    check("carry count is read back", parse_questions(
        q.replace("scope?", "scope?  ·  carried 4x"))[2][0]["carried"], 4)
    check("the answer text survives", parse_questions(
        q.replace("**Answer:**", "**Answer:** Cut it, say so at refinement."))[2][0]["answer"],
        "Cut it, say so at refinement.")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  " + f)
        return 1
    print("selftest: 8 cases pass. A question is open until its Answer block holds non-whitespace, "
          "a missing Answer marker counts as open rather than silently answered, and the carry "
          "count survives a round trip through the file.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="The ASK surface, answered in a file.")
    ap.add_argument("--date")
    ap.add_argument("--repo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("render"); p.add_argument("--in", dest="infile", default="-")
    p = sub.add_parser("parse"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("carry"); p.add_argument("--from", dest="prev")
    sub.add_parser("selftest")
    a = ap.parse_args()
    repo = pathlib.Path(a.repo).resolve() if a.repo else repo_root()
    ctx = Ctx(a.date or today(), repo)
    return {"render": cmd_render, "parse": cmd_parse, "carry": cmd_carry,
            "selftest": cmd_selftest}[a.cmd](ctx, a)


if __name__ == "__main__":
    sys.exit(main())
