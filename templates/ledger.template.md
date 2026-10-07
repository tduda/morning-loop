# Commitments & Ideas Ledger

Rolling memory of everything your meetings and messages throw off, carried across days until closed. The morning loop reconciles this file every run instead of re-deriving it, so nothing gets lost and dated items come back on their trigger date.

**Buckets:** `MINE` (my open actions), `WAITING_ON` (others owe me), `FUTURE` (deferred or dated), `IDEAS` (opportunities, unscoped), `DECISIONS` (made, needing follow-through). Tick `[x]` to close; the reconcile step never reopens a closed item.

**Entry fields:** `status` open/done/carried/dropped · `src` where it came from + date · `seen` first→last · `age` days open · `trigger` (FUTURE only) · `jira` linked key if any · `carry` how many runs it has been carried.

`last_reconciled: never`

---

## MINE: my open action items

## WAITING_ON: others owe me / I should chase

## FUTURE: deferred / dated (resurfaces when trigger hits)

## IDEAS: opportunities, not yet scoped

## DECISIONS: made, needing follow-through
