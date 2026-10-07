---
description: "Work the meeting-action queue: tickets, decisions and updates from your meetings in one file. See what was drafted, sync your ticked approvals, and act on the approved ones. Nothing happens without your tick and a confirmation per item."
argument-hint: "[empty to show today's queue | sync | create | a date]"
---

# /tickets, the meeting-action queue

`{PY}` below is the Python interpreter from `morning/config.yml` (`owner.python`: `py -3`, `python3` or `python`, found at setup). Use exactly that; if the key is missing, use `python3`.

Everything a meeting produces lives in one reviewable file, grouped by meeting, with a checkbox each: **tasks** go to your task tracker, **decisions** go to your decision log, **updates** go to a named channel. `$ARGUMENTS` is either empty, `sync`, `create`, or a date.

## Show (default)

```
{PY} morning/engine/tickets.py --date {DATE} status
```

If the queue is empty, say so in one line and stop. Otherwise report the counts and the queue path, name any **blocked** ticket with its reason, and name any **STUB** (a ticket whose source was a paraphrase, so it carries one confirm-scope criterion by rule rather than five invented ones). Do not read the tickets out. The file is the interface.

## Sync

After they have ticked boxes, `[x]` to build and `[-]` to drop:

```
{PY} morning/engine/tickets.py --date {DATE} sync
```

Report approved, dropped, still undecided. **If `sync` refuses a ticked box**, it is because that item fails a rule that has already produced a bad artifact. For a ticket: a missing house header, an invented criterion on a paraphrase source, a person as owner instead of a role, an unverified `KM-` reference. For a decision: it is hedged and was therefore discussed rather than decided, it is an action and belongs in a ticket, it has no rationale or no date, or it names a speaker from a summary-level source. For an update: no named channel, an unsourced number, or a hygiene-queue item, which never goes external. Say which, offer to re-draft that one item, and do not offer to bypass the check.

## Create

Only for tickets `sync` marked approved:

```
{PY} morning/engine/tickets.py --date {DATE} approved --json
```

Then, **one at a time**, confirming the destination before each:

- **ticket**: create the issue via Atlassian, confirming project and epic first
- **decision**: append to your decision log: `morning/decisions.md` by default, or the page or file named in config `decisions.home`. If someone else maintains it, add an entry, never restructure it
- **update**: post to the named channel

Record each immediately with its real destination:

```
{PY} morning/engine/tickets.py --date {DATE} done --id {t1} --key PROJ-1234
{PY} morning/engine/tickets.py --date {DATE} done --id {t2} --to "confluence 123456"
{PY} morning/engine/tickets.py --date {DATE} done --id {t3} --to "chat <channel name>"
```

That marks the queue and appends to the outbound ledger in one step. **Never record a key the Jira call did not return.** If Atlassian is unreachable, stop, say so, and leave the tickets approved: an approval survives to tomorrow, an invented key does not survive contact with anyone.

## Rules

- Creating a task, editing a shared page and posting to a channel are all in `permissions.never_auto`. A tick is not consent to act; it is consent to be asked.
- The file is regenerated from state on every command, so anything typed into it outside a checkbox is lost. Edits belong in a re-draft.
- A dropped ticket keeps its `reject:` reason. That reason is the most useful thing in the file next month.
