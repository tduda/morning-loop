#!/usr/bin/env python3
"""Mechanical age reconcile for the commitments ledger.

Every morning run must age every OPEN item in
`morning/state/ledger.md` forward to today. Three
consecutive runs wrote a throwaway version of this to /tmp and discarded it,
and before that the ledger went four runs without any reconcile at all. This is
the durable copy, so the step cannot be skipped for lack of a tool.

What it does, and nothing else:
  * for every open item (`- [ ]` block) it advances the `seen: ...→MM-DD` end
    date to today and bumps the structured `age:` day count by the number of
    days elapsed since `last_reconciled`;
  * it increments each open item's `carry: N` by ONE, because one reconcile is
    one morning run regardless of how many calendar days elapsed. `carry` was
    seeded on 2026-09-08 after the hygiene queue recorded that the carry ladder
    in the config was escalating at 2 and auto-solving at 3
    against items whose count was unknowable. Ranges ("38 to 40") bump both
    bounds. An open item with no `carry:` field is left alone rather than
    guessed at;
  * it rewrites the `last_reconciled:` line;
  * it inserts one italic reconcile note under that line.

It never touches closed `[x]` items, never adds or removes items, never changes
free-text prose (those ages drift and must be fixed by hand or by a run that
actually re-reads the sources), and never queries Jira, Amplitude or Granola.
A content reconcile is a different job.

Usage:
  python3 reconcile_ledger.py --date 2026-09-03            # dry run, prints the diff summary
  python3 reconcile_ledger.py --date 2026-09-03 --apply    # writes the file
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

from trust import repo_root  # noqa: E402  (cwd-first, works through the workspace link)

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
REPO = repo_root()
LEDGER = REPO / "morning/state/ledger.md"

RE_LAST = re.compile(r"`last_reconciled: (\d{4}-\d{2}-\d{2})`")
RE_SEEN = re.compile(r"(seen: [^·\n]*?→)(\d{2}-\d{2})")
# age: **28d** · age: 14d · age: **64 to 93 days, exact figure unavailable** · age: **28d, of which 22d past its trigger**
RE_AGE = re.compile(r"(age: (?:\*\*)?)(\d+)( to (\d+))?( ?d\b| days\b)")
RE_AGE_OFWHICH = re.compile(r"(, of which )(\d+)(d past its trigger)")
# carry: **12** · carry: **38 to 40 runs, exact figure unavailable (...)**
RE_CARRY = re.compile(r"(carry: (?:\*\*)?)(\d+)( to (\d+))?")


def item_blocks(lines: list[str]) -> list[tuple[int, int, bool]]:
    """Return (start, end, is_open) for every `- [ ]` / `- [x]` block."""
    starts = [i for i, l in enumerate(lines) if re.match(r"^- \[( |x)\] ", l)]
    blocks = []
    for n, s in enumerate(starts):
        e = starts[n + 1] if n + 1 < len(starts) else len(lines)
        # a block ends early at a heading or a horizontal rule
        for j in range(s + 1, e):
            if lines[j].startswith("#") or lines[j].strip() == "---":
                e = j
                break
        blocks.append((s, e, lines[s].startswith("- [ ] ")))
    return blocks


def reconcile(text: str, today: dt.date) -> tuple[str, dict]:
    m = RE_LAST.search(text)
    if not m:
        raise SystemExit("no `last_reconciled:` marker found; refusing to guess")
    last = dt.date.fromisoformat(m.group(1))
    delta = (today - last).days
    stats = {"last": last.isoformat(), "delta_days": delta, "open_items": 0, "seen_bumped": 0, "age_bumped": 0, "carry_bumped": 0, "closed_untouched": 0}
    if delta <= 0:
        return text, stats

    lines = text.split("\n")
    old_mmdd = last.strftime("%m-%d")
    new_mmdd = today.strftime("%m-%d")

    for s, e, is_open in item_blocks(lines):
        if not is_open:
            stats["closed_untouched"] += 1
            continue
        stats["open_items"] += 1
        for i in range(s, e):
            l = lines[i]
            if "seen:" in l:
                l2, n = RE_SEEN.subn(lambda mm: mm.group(1) + new_mmdd if mm.group(2) == old_mmdd else mm.group(0), l)
                stats["seen_bumped"] += n if l2 != l else 0
                l = l2
            if "age:" in l:
                def bump(mm):
                    a = int(mm.group(2)) + delta
                    if mm.group(3):
                        b = int(mm.group(4)) + delta
                        return f"{mm.group(1)}{a} to {b}{mm.group(5)}"
                    return f"{mm.group(1)}{a}{mm.group(5)}"
                l2, n = RE_AGE.subn(bump, l, count=1)
                if n:
                    stats["age_bumped"] += 1
                    l2 = RE_AGE_OFWHICH.sub(lambda mm: f"{mm.group(1)}{int(mm.group(2)) + delta}{mm.group(3)}", l2, count=1)
                l = l2
            if "carry:" in l:
                def bumpc(mm):
                    a = int(mm.group(2)) + 1
                    if mm.group(3):
                        return f"{mm.group(1)}{a} to {int(mm.group(4)) + 1}"
                    return f"{mm.group(1)}{a}"
                l2, n = RE_CARRY.subn(bumpc, l, count=1)
                if n:
                    stats["carry_bumped"] += 1
                l = l2
            lines[i] = l

    text = "\n".join(lines)
    text = RE_LAST.sub(f"`last_reconciled: {today.isoformat()}`", text, count=1)
    note = (
        f"\n_Last reconciled: **{today.isoformat()}** ({today.strftime('%A')}, {delta} calendar day{'s' if delta != 1 else ''} after the "
        f"{last.isoformat()} reconcile) · **{stats['open_items']} open items** aged **+{delta}**, {stats['seen_bumped']} `seen` end dates "
        f"advanced {old_mmdd}→{new_mmdd}, {stats['age_bumped']} structured `age:` fields bumped, {stats['carry_bumped']} `carry:` counts "
        f"incremented by one run. **{stats['closed_untouched']} closed `[x]` "
        f"items untouched.** Applied by `morning/engine/reconcile_ledger.py`, the durable reconciler, so this step no longer "
        f"depends on a throwaway script. **Mechanical pass only:** Jira, Amplitude and Granola were not queried by this script, so every status "
        f"line below is exactly as stale as it already said it was, and free-text day counts in item prose were not touched._\n"
    )
    text = text.replace(f"`last_reconciled: {today.isoformat()}`\n", f"`last_reconciled: {today.isoformat()}`\n{note}", 1)
    return text, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ledger", default=str(LEDGER))
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.date)
    p = Path(a.ledger)
    text = p.read_text()
    new, stats = reconcile(text, today)
    print(stats)
    if stats["delta_days"] <= 0:
        print("nothing to do: ledger already reconciled to or past this date")
        return 0
    if a.apply:
        p.write_text(new)
        print(f"written {p}")
    else:
        print("dry run; pass --apply to write")
    return 0


if __name__ == "__main__":
    sys.exit(main())
