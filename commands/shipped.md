---
description: "Record something that just left the workspace under your name: a Confluence page published, Jira tickets created, a Mattermost post, an email sent. Appends to the outbound ledger with the draft's verification state read from its trust stamp."
argument-hint: "[what you sent and where, in plain words: \"the weekly update, to the team Confluence page\"]"
---

# /shipped, the outbound record

`{PY}` below is the Python interpreter from `morning/config.yml` (`owner.python`: `py -3`, `python3` or `python`, found at setup). Use exactly that; if the key is missing, use `python3`.

**The problem this closes.** `shipped: 0` in the run log counts only what the *loop* sent. Everything the owner reads, edits and posts by hand is untracked, so nothing anywhere answers *"what went out under my name last week, to which page, from which draft, and had it been verified when it went?"*. The hand path is the majority of sends and it was the invisible one.

## What to do

1. **Work out what was sent, and where.** `$ARGUMENTS` is plain words. Resolve it to:
   - the **job**: prefer the routing rule id or the draft's job id (`gc_update`, `meeting_debrief`, `sprint_package`). Check the day's stamps first: `ls morning/drafts/{DATE}/.trust/`. If the send has no draft behind it, use a short kebab-case name and say so.
   - the **destination**, as an identifier and not a description: a Confluence page id, a Jira key, a named channel, a recipient. `"confluence 123456 (team page)"` is a ledger row; `"the team page"` is not.
   - the **date** it went (default today) and **who sent it** (`--by hand` unless the loop did it).
2. **Ask only if the destination is genuinely ambiguous.** One closed question, then proceed. Do not interrogate.
3. **Record it:**

```
{PY} morning/engine/shipped.py add \
  --job {job} --to "{destination}" --by hand [--date {DATE}] [--note "{anything the row needs}"]
```

The `verified` column is **read from the trust stamp**, never typed. If the draft went out `UNVERIFIED`, `SELF-ASSESSED` or on `HOLD`, the ledger says so permanently and the command exits 1. **That is the correct outcome, not an error to work around.** A ledger that cannot embarrass the loop is decoration. Report the exit honestly and do not re-run it with different flags to get a cleaner row.

4. **Confirm in one line**, naming the verification state:
   `Recorded: gc_update → confluence 123456 · verified-at-send: no (UNVERIFIED) · ledger now holds 14 sends, 6 unverified.`

## Reading it back

```
{PY} morning/engine/shipped.py list --since 2026-08-21
{PY} morning/engine/shipped.py list --unverified
```

Use these when someone asks about something published under your name: the ledger has the row, the source draft and its verification state at the moment it went, which is the question, rather than a reconstruction from memory.

## Rules

- **Append-only.** A row is never edited after it is written. A mistake is corrected by a new row with a `--note`, the same way a ledger works everywhere else.
- **Record what left, never what was intended.** A ship that was cancelled mid-queue leaves no row.
- **The ledger is not a to-do list.** It is evidence. Its only job is to be true.
