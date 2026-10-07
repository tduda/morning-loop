---
name: meeting-debrief
description: "Turns meeting notes or a transcript into decisions, action items (owner, due), open questions and draft tasks, and flags when the source is only a summary. Use on \"debrief this meeting\", \"what came out of this\", \"extract action items\", when a transcript is pasted in, or when /morning finds new meeting notes."
---

# meeting-debrief: from talk to tracked work

The debrief is the bridge between a meeting and the work it created. Its value is in what it refuses to make up.

## Inputs

| input | where | required |
|---|---|---|
| notes or transcript | pasted in, a file in `morning/notes/`, or a meetings-source finding | yes |
| source kind | `transcript` (verbatim) or `summary` (paraphrase, AI notes, someone's bullets) | yes; decide in step 1 |
| ledger | `morning/state/ledger.md` | yes |
| open tasks | tasks source, if on | no |
| examples | `morning/examples/meeting-debrief/` | no |

## Steps

1. **Classify the source.** Verbatim transcript with speaker turns = `transcript`. Anything else (AI meeting notes, a recap, bullets) = `summary`. When unsure, treat it as `summary`. Print the classification at the top.
2. **Check for an existing debrief** of the same meeting in `morning/drafts/` and `morning/notes/`. If one exists, update it rather than writing a second.
3. **Extract decisions.** Only things that were decided, not things that were discussed. Each gets an owner (who made or holds it) and a confidence: `firm` (stated as decided), `tentative` (agreed pending something), `unclear` (sounded decided, nobody said so). If nothing was decided, write "no decisions recorded".
4. **Extract action items.** Each needs an owner and a due date. If the source names neither, the owner is `unassigned` and the item goes to Open questions as "who owns {action}?". A due date not stated is `due: not set`, never guessed.
5. **Extract open questions.** Each names who can answer it and what waits on it.
6. **Draft tasks** for actions that belong in a task tracker:
   - From a `transcript`: title, one-line why (citing the moment in the meeting), and acceptance criteria only where the transcript states them.
   - From a `summary`: a **stub** with exactly one criterion, `confirm scope with <owner>`. No other criteria, however obvious they seem.
   - Any task whose scope the source does not make clear is a stub, even from a transcript.
7. **Propose ledger lines.** Every action the user owns, and every action someone owes the user, as a ledger line for the user to accept. Do not write the ledger directly.

## Output

Write to `morning/drafts/{DATE}/debrief-{meeting-slug}.md`, and append task drafts to `morning/drafts/{DATE}/meeting-actions.md`.

```markdown
# Debrief: {meeting title}, {date}

**Source:** {transcript | summary} ({where it came from})
{if summary: "Summary-level source. No quotes are attributed, and task drafts are stubs."}

## Decisions
- {decision} (owner: {name}; confidence: firm | tentative | unclear)

## Action items
| action | owner | due | source |
|---|---|---|---|
| {verb-first action} | {name or unassigned} | {date or not set} | {timestamp, line, or section} |

## Open questions
- {question} (who can answer: {name or role}; waiting on it: {what})

## Draft tasks
### {title}
Why: {one line, citing the meeting}
Acceptance criteria:
- [ ] confirm scope with {owner}          <- the only criterion on a stub
Status: stub | ready to create

## Proposed ledger lines
- [ ] you owe {person}: {item}, due {date or not set}
- [ ] {person} owes you: {item}, due {date or not set}
```

## Never

- Never invent acceptance criteria from a summary. A summary-sourced task ships as a stub with one criterion, `confirm scope with <owner>`. Five plausible criteria are a validation error, not a better draft.
- Never put words in quotes against a named person from a summary-level source.
- Never promote a discussion to a decision to fill the section.
- Never guess an owner or a date. `unassigned` and `not set` are correct answers.
- Never create tasks, post notes or message attendees. Everything here is a draft.

## Degrading

| situation | effect |
|---|---|
| tasks source off | task drafts are still written, marked "not created: tasks source off" |
| no speaker labels | treat as `summary` |
| meeting has no notes at all | write nothing; report "no notes found for {meeting}" |
| ledger unreadable | skip proposed ledger lines and say so |
