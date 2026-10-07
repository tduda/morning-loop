---
name: stall-check
description: "Finds tasks that are stuck (no movement for N days, blocked, in review too long) and turns each into one named next action with an owner: a mechanical SOLVE or a closed ASK to a named person, escalating instead of repeating. Use on \"what's stuck\", \"stalled tasks\", \"this has been in review for days\", or when /morning fires a task_state job."
---

# stall-check: a name and a next step, never a nag

Detecting a stall is not the job. Closing it is. A stall reported in the same words every morning teaches the reader to skip the section, so every stall leaves this skill as either a SOLVE or an ASK.

## Inputs

| input | where | required |
|---|---|---|
| open tasks with history | tasks source: status, assignee, and the status-change history | yes |
| thresholds | config `stall.thresholds` (defaults below) | no |
| scope | config `sources.tasks.scope` (the filter that makes a task the user's or their team's) | yes |
| past reports | `morning/drafts/*/stall-check.md`, for the report count | no |
| decisions | debriefs and `morning/notes/`, for consciously parked work | no |

## Default thresholds

Age alone is not a stall. A task in a backlog for 90 days is a backlog.

| state | stalled after | usual cause |
|---|---|---|
| in review | 2 days | nobody was asked, or the reviewer is away |
| ready to release or deploy | 3 days | nobody owns the release step |
| in progress | 5 days | blocked but not marked, or bigger than thought |
| ready, in the current cycle | 5 days | unassigned, or the cycle took on too much |
| blocked | 2 days | the blocker has no owner or no date |

Map the user's own status names onto these in config. Users can change any number.

## Steps

1. **Pull in-scope tasks** with the scope filter. Report the unscoped count beside it when the project is shared.
2. **Date each status from its history,** not from the "updated" field. A label or field edit is not movement. If history is not available, say "age from updated field, may be wrong" on every line.
3. **Keep only tasks past their threshold.** Drop anything parked by a recorded decision, and say how many were dropped and why.
4. **Find the why** from history and comments: last real transition, who acted last, what the last comment asks.
5. **Type the next step.**
   - **SOLVE**: needs no one's judgement. Request review from a named reviewer, move the task to the state it has actually reached, link a forgotten dependency, draft the release note. Done only on the user's yes.
   - **ASK**: one fact unblocks it. A closed question to the one person who can answer. If nobody knows who that is, the question is "who owns {step}?", addressed to whoever can name them.
6. **Escalate instead of repeating.** Count past reports. Second report: the ASK also goes to the person's lead (as a draft). Third or later: add a Process finding naming what is structurally broken.

## Output

Write to `morning/drafts/{DATE}/stall-check.md`.

```markdown
# Stalled ({n})
Scope: {filter} ({n} in scope, {n} unscoped). Parked by decision, not listed: {n}.

## {task title} [{id}] · {state} {N}d · reported {M}x
{one line: why, from history}
-> SOLVE: {mechanical step}
-> ASK {person}: {closed question}

## Process finding
{only when something has been reported 3 or more times: what is broken, and where to raise it}
```

## Never

- Never emit a stall without a SOLVE or ASK. An observation is not an output.
- Never address an ASK to "the team" or to the assignee by default when the answer sits elsewhere.
- Never put a judgement call in a SOLVE. If it needs a decision, it is an ASK.
- Never repeat yesterday's line verbatim. Escalate, or say plainly "asked {M} times, no answer".
- Never surface a task outside the user's scope, and never surface a backlog item as a stall.
- Never move a task, comment or ping anyone without a per-item yes.

## Degrading

| situation | effect |
|---|---|
| tasks source off | do not run; report "no task source on" |
| no status history | age from updated field, flagged on every line |
| no past reports | report count starts at 1 |
| no decision notes | header says "decisions not checked" |
