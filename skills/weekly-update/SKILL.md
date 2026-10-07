---
name: weekly-update
description: "Drafts a weekly update for a manager or stakeholders from the week's ledger, closed tasks, meetings and pinned metrics: what moved, what is blocked, what is next, written in the user's voice learned from their saved examples. Use on \"write my weekly update\", \"status update for my manager\", or when /morning fires the weekly job."
---

# weekly-update: the week, in your words

A weekly update is read by someone with ten other updates to read. It has to say what changed and what the reader needs to do, in the voice they already know from you.

## Inputs

| input | where | required |
|---|---|---|
| the week | last complete Monday to Sunday, or Monday to today when run on a Friday; state which | yes |
| ledger | `morning/state/ledger.md`, lines closed or added this week | yes |
| briefs | `morning/briefs/` for the week | yes |
| closed and moved tasks | tasks source, if on | no |
| meeting debriefs | `morning/drafts/*/debrief-*.md` and `morning/notes/` for the week | no |
| pinned metrics | `metrics-pulse` output, if on | no |
| goals | `morning/profile.md` | yes |
| audience | config `jobs[].audience` or ask once: manager, team, stakeholders | yes |
| voice examples | `morning/examples/weekly-update/` (past updates the user actually sent) | strongly recommended |
| last update | the most recent file in that folder, or the last weekly draft | no |

## Steps

1. **Read the examples first.** Note length, structure, greeting, how they talk about blockers, whether they use bullets, headers or emoji. The draft copies that shape. With no examples, use the template below and say in the header note that the voice is generic until examples are saved.
2. **Read last week's update** if there is one. Anything it said was "next" gets an outcome this week: done, moved, or dropped (and why).
3. **Collect what moved.** Closed tasks, closed ledger lines, decisions from debriefs. Group by goal from the profile; leave out what serves no goal unless the reader would expect it.
4. **Collect what is blocked.** Open items with a named blocker. Each blocker says who or what it waits on and what the reader could do about it, if anything.
5. **Collect what is next.** Open ledger lines and planned tasks for next week. Three to five items.
6. **Add numbers only from sources.** Pinned metrics come from metrics-pulse with their window. A number with no source is left out, not estimated.
7. **Write in the user's voice.** First person, their sentence length, their level of formality. Keep opinions and uncertainty they would state.

## Output

Write to `morning/drafts/{DATE}/weekly-update.md`. If the examples have a different shape, follow the examples.

```markdown
<!-- week: {start} to {end}; audience: {audience}; voice: examples ({n}) | generic -->

{greeting line, if the examples use one}

**What moved**
- {outcome, not activity} ({source})

**Blocked**
- {item}: waiting on {person or thing} since {date}. {what would help}

**Next week**
- {item}

**Numbers** (only if pinned metrics are on)
- {metric}: {value} vs {prior} ({window}, {source})

{sign-off, if the examples use one}
```

## Never

- Never claim something moved that the sources do not show as moved. "Worked on" is not "shipped".
- Never invent or round a number to make it read better. No source, no number.
- Never drop last week's "next" items silently.
- Never send or post. Sending needs the user's per-item yes.
- Never invent a voice. Without examples, write plainly and say the voice is generic.

## Degrading

| source off | effect |
|---|---|
| tasks | "What moved" comes from the ledger, briefs and debriefs; header notes tasks were not read |
| meetings | no decisions section input; noted |
| metrics | no Numbers section at all, not an empty one |
| no examples | generic shape, flagged in the header comment and in the brief |
| ledger and briefs both empty | write nothing; report "not enough this week to draft from" |
