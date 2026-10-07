---
name: meeting-prep
description: "Writes a short prep note for one meeting today or tomorrow: its purpose, what each attendee has open with the user, the decisions needed, and three questions to ask. Use on \"prep me for my 2pm\", \"what do I need for the planning meeting\", or when /morning fires a calendar job for an upcoming meeting."
---

# meeting-prep: one meeting, one page

A prep note is read in the two minutes before a meeting. If it takes longer than that to read, it failed.

## Inputs

| input | where | required |
|---|---|---|
| the meeting | calendar finding (title, time, attendees, description, links) or the user names it | yes |
| ledger | `morning/state/ledger.md` | yes |
| past notes for this meeting | `morning/notes/`, plus the meetings source if on | no |
| open tasks involving attendees | tasks source, if on | no |
| inbox and chat threads with attendees | last 14 days, if on | no |
| goals | `morning/profile.md` | yes |
| examples | `morning/examples/meeting-prep/` | no |

## Steps

1. **Pin the meeting.** Title, start time with timezone, attendees, and the stated agenda or description verbatim. If there is no agenda, say so; do not invent one.
2. **Work out the purpose.** In this order: the stated agenda; the last note of this recurring meeting; the invite description. If none of these says why the meeting exists, the purpose line is `not stated` and question 1 becomes "what do we need to leave this meeting with?".
3. **Collect open items per attendee.** For each attendee, from the ledger, tasks, and recent threads: what the user owes them, what they owe the user, and anything waiting on either side. Each item carries its source. An attendee with nothing open gets no line.
4. **Find the decisions needed.** Only decisions that something in the sources actually points at (an open question in last time's notes, a task waiting on a choice, a thread asking "should we"). Name who decides.
5. **Write three questions.** Closed where possible, each tied to a decision or an open item, each addressed to a named attendee. No warm-up questions.
6. **Check against examples** if any exist in `morning/examples/meeting-prep/` and match their length and tone.

## Output

Write to `morning/drafts/{DATE}/prep-{meeting-slug}.md`.

```markdown
# Prep: {meeting title}, {day} {HH:MM} {TZ}

**Purpose:** {one sentence, with its source} | not stated
**Attendees:** {names or roles, as the invite lists them}

## Open with you
- **{attendee}**: you owe {item} ({source}); they owe {item} ({source})

## Decisions needed
- {decision} (decides: {person}; source: {where it came from})
- none found in the sources

## Ask
1. {attendee}: {question}
2. {attendee}: {question}
3. {attendee}: {question}

## Last time
{one or two lines from the last note of this meeting, or "no previous notes found"}
```

## Never

- Never invent an agenda, a decision, or an open item. An empty section says it is empty.
- Never quote an attendee from a summary-level note. Paraphrase is reported as "the notes say", not as a quote.
- Never send the note or message an attendee. It is a draft for the user.
- Never pad to three questions with generic ones ("any blockers?"). Fewer, real questions beat three filler ones; say "only {n} real questions found".
- Never assume the user's role in the meeting. If the invite does not show it, leave it out.

## Degrading

| source off | effect |
|---|---|
| calendar | runs only when the user names the meeting and its attendees |
| tasks | "Open with you" uses the ledger and threads only, and says tasks were not read |
| inbox and chat | no thread items; noted under the header |
| no past notes | "Last time" says so |
| everything but the ledger off | still useful: what you owe each attendee, plus three questions from the ledger |
