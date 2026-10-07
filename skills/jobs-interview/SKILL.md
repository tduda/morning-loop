---
name: jobs-interview
description: "Onboarding stage 6. Mines profile.md, the ledger, a week of briefs and the user's files to draft their recurring jobs, interviews to fill gaps, grades each job honestly (automatable? which skill? needs examples first?) and proposes routing rules for config.yml. Use on \"set up my jobs\", \"what can the loop do for me\", or when /onboard reaches stage 6."
---

# jobs-interview: what you do every week, and what the loop can take

Stage 6 runs after about a week of briefs, because a week of real output is better evidence than anyone's memory of their own job. The output is a list of jobs and a block of routing rules the user pastes (or approves) into `morning/config.yml`.

## Inputs

| input | where | required |
|---|---|---|
| profile | `morning/profile.md` | yes |
| ledger | `morning/state/ledger.md` | yes |
| briefs | `morning/briefs/`, the last 5 to 10 | yes |
| run log | `morning/state/run-log.md` | no |
| the user's files | the folder `morning/` lives in, files changed in the last 3 weeks (names and headings only unless the user agrees to more) | no |
| calendar | recurring events, if the source is on | no |
| installed skills | `skills/*/SKILL.md` in the package, frontmatter only | yes |
| examples | `morning/examples/<skill>/` (which skills already have examples) | no |

## Steps

1. **Mine before asking.** From the inputs, draft 5 to 12 recurring jobs. Evidence that something is a job: it recurs in the ledger, in briefs, as a recurring meeting, or as a file the user makes again and again. Each draft job carries the evidence that suggested it.
2. **Show the draft and correct it.** Ask the user to remove what is not theirs or not recurring, add what no tool can see, and fix the level of detail. One-off projects are not jobs.
3. **Push each job to buildable altitude.** "Manage stakeholders" is too high. "Write the Friday update for my manager from what closed this week" is right. For each job, fill in: what, how often, trigger, inputs, output, who receives it. Ask past-behaviour questions ("walk me through last time") rather than "how would you".
4. **Split meetings.** The meeting itself stays human. Its prep and its follow-up are separate jobs, usually `meeting-prep` and `meeting-debrief`.
5. **Grade each job honestly.**
   - **Automatable?** `yes` (an installed skill can draft it), `partly` (a skill does the gathering, the user does the judgement), `no` (relationship, judgement, presence).
   - **Skill:** the installed skill that matches, by name. If none matches, `none`. Do not invent a skill and do not stretch one to fit.
   - **Needs examples first?** `yes` when the output must sound like the user or match a house format and `morning/examples/<skill>/` is empty. Say how many examples to save (two or three is usually enough).
   - **Output mode:** `draft` (user reviews before it goes anywhere), `auto` (read-only, shown in the brief), `decide` (needs the user's call), `human` (the loop only reminds).
6. **Propose routing rules** in the exact shape below. Jobs with no skill are written commented out with the reason, so the user sees what is missing.
7. **Ask before writing.** Show the block. Write it into `morning/config.yml` under `jobs:` only on the user's yes, and never overwrite an existing job with the same id without showing the difference.

## Routing rule shape

```yaml
jobs:
  - id: weekly_update
    when: weekly            # daily | weekly | calendar | task_state | meeting_new | metric_move
    weekday: fri
    skill: weekly-update
    output: draft           # draft (you review) | auto (read-only, shown in brief) | decide (needs you) | human
    sends_to: none          # none | the tool it would be sent to; sending always needs your per-item yes
```

Field rules: `weekday` only with `weekly`. `calendar` jobs may add `match:` (words in the event title). `task_state` jobs fire from stall-check findings. `meeting_new` fires when new notes arrive. `metric_move` fires when metrics-pulse flags a pinned metric. `sends_to` is never anything but `none` unless the user named the tool.

## Output

Write to `morning/drafts/{DATE}/jobs.md`.

````markdown
# Your recurring jobs ({n})

| job | how often | inputs | output | goes to | automatable | skill | examples first? | evidence |
|---|---|---|---|---|---|---|---|---|
| {what} | {cadence} | {inputs} | {output} | {who} | yes / partly / no | {skill or none} | yes ({n}) / no | {where seen} |

## Kept human
- {job}: {why it stays human}; what the loop can do around it: {prep, reminder, or nothing}

## Save examples for
- `morning/examples/{skill}/`: {n} past {outputs}, because {reason}

## Proposed routing rules
```yaml
jobs:
  - id: ...
  # - id: {job_id}          # no skill: {reason}. Stays manual for now.
```
````

## Never

- Never invent a skill, or route a job to a skill whose description does not cover it.
- Never call a job automated because a skill exists. A skill the user triggers and rewrites every time is still manual work; say so.
- Never set `sends_to` to a tool, or `output: auto` on anything that leaves the machine, without the user saying so.
- Never write config without a yes.
- Never read file contents beyond names and headings without asking.

## Degrading

| situation | effect |
|---|---|
| fewer than 3 briefs | warn that evidence is thin; lean on the interview |
| ledger empty | jobs come from briefs, files and the interview |
| calendar off | ask about recurring meetings directly |
| user skips the interview | write the mined draft only, every job marked `unconfirmed`, rules all commented out |
