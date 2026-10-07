#!/usr/bin/env python3
"""
shipped.py: the outbound record (QW4).

Why this exists
---------------
Nothing recorded what actually left the workspace. `shipped: 0` in the run log
counts only loop-initiated sends, so everything the owner posts by hand after reading
a draft is invisible. There was no artifact anywhere that answered:

    what went out under my name last week, to which page, from which draft,
    and had it been verified when it went?

This is that artifact. Append-only, two files that stay in step:

    morning/state/outbound-ledger.md      readable, one row per send
    morning/state/outbound-ledger.jsonl   machine-readable, same rows

The verified-at-send column is NOT typed in by hand. It is read from the trust
stamp for that job on that date, so a draft that went out ungraded says so in the
ledger forever. That is the point: the ledger has to be able to embarrass the loop
or it is decoration.

    shipped.py add --job weekly_update --to "confluence 123456" --by hand
    shipped.py list --since 2026-08-21
    shipped.py list --unverified

Exit codes: 0 fine · 1 recorded, but it went out unverified · 2 usage error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from trust import (Ctx, grade, load_corrections, repo_root, today,  # noqa: E402
                   READY, HOLD, UNVERIFIED, SELF_ASSESSED, PARTIAL, NEEDS_EDIT)

LEDGER_MD = "morning/state/outbound-ledger.md"
LEDGER_JSONL = "morning/state/outbound-ledger.jsonl"
BRIEF_INDEX = "morning/state/brief-index.json"

HEADER = """# Outbound ledger

Every artifact that left this workspace under your name, one row per send.

**The `verified` column is read from the trust stamp at the moment of sending, not
typed in.** `yes` means an independent verifier cleared every check before it went.
`self` means the drafting context graded its own work. `no` means it went out with
no grading at all. A row is never edited after it is written.

Written by the loop when it ships, and by `/shipped` when the owner ships by hand. The
hand path is the one that matters: it is the path that used to be invisible.

| date | time | job | destination | verified | draft | brief | by |
|---|---|---|---|---|---|---|---|
"""

VERIFIED_FROM_VERDICT = {
    READY: "yes",
    NEEDS_EDIT: "no",
    PARTIAL: "partial",
    SELF_ASSESSED: "self",
    UNVERIFIED: "no",
    HOLD: "no (held)",
}


def die(msg: str, code: int = 2):
    print(f"shipped.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def brief_id_for(repo: pathlib.Path, date: str) -> str:
    p = repo / BRIEF_INDEX
    if not p.exists():
        return ""
    try:
        idx = json.loads(p.read_text())
    except json.JSONDecodeError:
        return ""
    for b in (idx.get("briefs") or {}).values():
        if b.get("date") == date:
            return f"#{b.get('id')}"
    return ""


def stamp_for(repo: pathlib.Path, date: str, job: str) -> tuple[str, str, str]:
    """(verified, verdict, artifact) read from the day's trust stamp."""
    ctx = Ctx(date, repo)
    sp = ctx.stamp_path(job)
    if not sp.exists():
        return "no", "NO STAMP", ""
    stamp = json.loads(sp.read_text())
    g = grade(stamp, load_corrections(ctx))
    return (VERIFIED_FROM_VERDICT.get(g["verdict"], "no"), g["verdict"],
            stamp.get("artifact") or "")


def cmd_add(repo: pathlib.Path, a) -> int:
    date = a.date or today()
    if not a.to:
        die("--to is required: name the page id, ticket key or channel it went to")
    verified, verdict, artifact = stamp_for(repo, date, a.job)
    draft = a.draft or artifact or ""

    row = {
        "date": date,
        "time": a.time or _dt.datetime.now().strftime("%H:%M"),
        "job": a.job,
        "destination": a.to,
        "verified_at_send": verified,
        "verdict_at_send": verdict,
        "draft": draft,
        "brief": a.brief or brief_id_for(repo, date),
        "by": a.by,
        "note": a.note or "",
        "recorded_at": _dt.datetime.now().replace(microsecond=0).isoformat(),
    }

    md = repo / LEDGER_MD
    md.parent.mkdir(parents=True, exist_ok=True)
    if not md.exists():
        md.write_text(HEADER)
    line = ("| {date} | {time} | {job} | {destination} | **{verified}** | {draft} "
            "| {brief} | {by} |").format(
        date=row["date"], time=row["time"], job=row["job"],
        destination=row["destination"], verified=row["verified_at_send"],
        draft=f"`{draft}`" if draft else "none",
        brief=row["brief"] or "-", by=row["by"])
    if row["note"]:
        line += f"\n| | | | | | | | {row['note']} |"
    with md.open("a") as f:
        f.write(line + "\n")

    jl = repo / LEDGER_JSONL
    with jl.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"recorded: {a.job} → {a.to} · verified-at-send: {verified} ({verdict})")
    if verified != "yes":
        print("  This went out without an independent verifier clearing it. "
              "The ledger says so, permanently, and that is correct.")
        return 1
    return 0


def cmd_list(repo: pathlib.Path, a) -> int:
    jl = repo / LEDGER_JSONL
    if not jl.exists():
        print("outbound ledger is empty: nothing has been recorded as sent yet.")
        return 0
    rows = [json.loads(ln) for ln in jl.read_text().splitlines() if ln.strip()]
    if a.since:
        rows = [r for r in rows if r["date"] >= a.since]
    if a.job:
        rows = [r for r in rows if r["job"] == a.job]
    if a.unverified:
        rows = [r for r in rows if r["verified_at_send"] != "yes"]
    if not rows:
        print("nothing matches.")
        return 0
    for r in rows:
        print(f"{r['date']} {r['time']}  {r['job']:<24} -> {r['destination']}")
        print(f"    verified-at-send: {r['verified_at_send']} ({r['verdict_at_send']})"
              f"  by: {r['by']}  brief: {r['brief'] or '-'}")
        if r.get("draft"):
            print(f"    draft: {r['draft']}")
    unver = [r for r in rows if r["verified_at_send"] != "yes"]
    print(f"\n{len(rows)} sent · {len(unver)} without an independent verifier.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="The outbound record.")
    ap.add_argument("--repo")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="record one artifact leaving the workspace")
    p.add_argument("--job", required=True)
    p.add_argument("--to", required=True, help="page id, ticket key, channel")
    p.add_argument("--draft", help="source draft path; read from the stamp if omitted")
    p.add_argument("--date")
    p.add_argument("--time")
    p.add_argument("--brief")
    p.add_argument("--by", choices=["loop", "hand"], default="hand")
    p.add_argument("--note")

    p = sub.add_parser("list", help="what went out")
    p.add_argument("--since")
    p.add_argument("--job")
    p.add_argument("--unverified", action="store_true")

    a = ap.parse_args()
    repo = pathlib.Path(a.repo).resolve() if a.repo else repo_root()
    return {"add": cmd_add, "list": cmd_list}[a.cmd](repo, a)


if __name__ == "__main__":
    sys.exit(main())
