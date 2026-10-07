---
name: inbox-triage
description: "Ranks inbox and chat items into needs-reply, decide, FYI and noise, each with a one-line WHAT, WHY and HOW and a link, and captures promises the user made (\"I'll send it Friday\") as proposed ledger lines. Use on \"triage my inbox\", \"what needs my attention\", \"catch me up on messages\", or when /morning runs the inbox job."
---

# inbox-triage: understand first, act later

This is situational awareness, not inbox zero. Every item says what it is and why it landed in its bucket. Nothing is replied to, archived or marked read.

## Inputs

| input | where | required |
|---|---|---|
| inbox items | inbox source: unread plus the last 24 hours (72 on Monday), or since the last triage | one of inbox or chat |
| chat items | chat source: mentions, direct messages, threads the user posted in | one of inbox or chat |
| goals | `morning/profile.md` | yes |
| ledger | `morning/state/ledger.md` | yes |
| sent items | the user's own sent messages and chat posts in the window, for promise capture | no |
| corrections | `morning/state/triage-log.md`, past re-bucketings by the user | no |

## Steps

1. **Read, do not touch.** Pull items read-only. Record sender, channel, time and a link for each.
2. **Resolve notifications to their object.** A notification about a task or document is judged on the current state of that object (if the tool is connected), not on the notification text. If it cannot be resolved, mark it `unresolved` and rank it conservatively.
3. **Score each item** on signals you can name:
   - waiting on you: a direct question, a mention, an assignment, a request
   - goal link: names something from the profile's goals (say which goal and which words matched)
   - time: a deadline or decision window in the text
   - ownership: yours vs copied in
   - reversibility: a hard-to-undo decision outranks a routine acknowledgement
4. **Bucket.**
   - **Needs reply**: someone is waiting on an answer only the user can give.
   - **Decide**: a choice is being asked of the user, or will be made without them.
   - **FYI**: worth knowing, nothing to do.
   - **Noise**: newsletters, automated mail, resolved threads. Grouped with counts.
5. **Apply past corrections.** If the user re-bucketed a sender or pattern before, follow that and note it.
6. **Capture promises.** Scan the user's own messages in the window for commitments ("I'll send it Friday", "let me check and come back"). Each becomes a proposed ledger line with the quote, recipient and due date (`not set` if none was said).

## Output

Write to `morning/drafts/{DATE}/inbox-triage.md`.

```markdown
# Inbox {DATE}: {n} needs reply, {n} decide, {n} FYI, {n} noise
Sources: inbox {read | off | unavailable}, chat {read | off | unavailable}

**State of things:** {2 to 4 lines: who is waiting, what decision is live, what is heating up}

## Needs reply
- **WHAT** {who wants what} · **WHY** {signals that fired} · **HOW** {the answer needed, or the one fact to find first} · {link}

## Decide
- **WHAT** · **WHY** · **HOW** {the options as stated, and by when} · {link}

## FYI
- **WHAT** · **WHY** {why it is informational} · {link}

## Noise
- {group}: {count} ({senders})

## Promises you made
- [ ] "{your words}" to {person}, {channel}, due {date or not set}

Mis-bucketed something? Say which, and I will remember it.
```

## Never

- Never reply, send, archive, label, mark read or acknowledge anything. Any of those needs a separate, per-item yes.
- Never present an item as a bare action ("reply to X") without its WHY and link.
- Never summarise a notification from its subject line when the object could not be read; say `unresolved`.
- Never claim a goal link without naming the goal and the words that matched.
- Never hide FYI or Noise to make the digest shorter. Group them; do not drop them.
- Never write promises straight to the ledger. They are proposed lines the user ticks.

## Degrading

| situation | effect |
|---|---|
| inbox off, chat on (or the reverse) | triage the one that is on; header says which |
| both off | do not run; report "no inbox or chat source on" |
| connector down | header line "inbox not read: {error}"; no invented items |
| no goals in profile | rank on waiting-on-you, time and ownership only; say so |
| sent items unreadable | skip promise capture and say so |
