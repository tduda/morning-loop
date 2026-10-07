# Rubrics

The quality bar each drafting skill is graded against before its draft reaches you. The verifier grades a draft **check by check** (pass or fail, plus one sentence why) instead of giving it one overall score, and a draft that fails goes back to its drafter with the specific failed checks to fix.

## How a rubric is found

Skill `X` resolves to `rubrics/X.rubric.yml`. The filename must match the skill's folder name under `skills/`. Every skill rubric **extends `_base.rubric.yml`**, which holds the universal checks (grounded, traceable, sources declared, complete, format, no side effects, ready to ship). A skill with no rubric of its own is graded on `_base` alone. That is a real gap, not coverage: `_base` knows nothing job-specific.

| skill | rubric |
|---|---|
| meeting-prep | `meeting-prep.rubric.yml` |
| meeting-debrief | `meeting-debrief.rubric.yml` |
| weekly-update | `weekly-update.rubric.yml` |
| inbox-triage | `inbox-triage.rubric.yml` |
| stall-check | `stall-check.rubric.yml` |
| jobs-interview | `jobs-interview.rubric.yml` |
| today, metrics-pulse | none: they produce findings, not drafts. Their claims go through the claim verifier instead. |

## Format

```yaml
schema_version: 1
extends: _base                 # skill rubrics inherit the base checks
task: "one line: what this drafter produces"
calibration_target: "who the output must satisfy, and what 'good enough to use as-is' means"
created: YYYY-MM-DD
goldens:                       # outputs the checks were calibrated against
  - path: "morning/examples/<skill>/<file>"
    note: "why it is good"
known_reject:                  # a described bad output the rubric MUST fail
  - "flat description of a bad output, ending with the checks it must fail"
checks:
  - id: snake_case_id
    type: structural | binary_llm      # structural = checkable mechanically; binary_llm = needs judgement
    severity: block | gate | normal
    scope: voice | format | data
    statement: "the check, phrased so a grader can return pass or fail"
    rationale: "why this is a check: the failure it prevents"
```

**Severity.**
- `block`: a fail is a hard NEEDS-EDIT, never shippable, however many revisions are left. Used for invented facts, actions taken without a yes, and anything else that cannot be undone once it reaches a reader.
- `gate`: the ship test for that skill. One per rubric, usually.
- `normal`: counts toward READY and can be fixed in a revision.

**Scope.** `data` checks are about what is true; `format` checks are about the current shape of the output and may change with the template; `voice` checks are about how it reads.

## Grading contract

1. Resolve the rubric: `_base` checks plus the skill's checks.
2. Grade each check on its own: "Apply this single check to the artifact. Return pass or fail and one sentence why."
3. The draft is **READY** only if every check passes. Any `block` fail means NEEDS-EDIT regardless of revisions left.
4. On a fail, within `quality.max_revisions` in config, hand the drafter the failed checks' statements and reasons (never a vague note), let it revise once, and grade again.
5. Log each check's result to `morning/drafts/{DATE}/.trust/`, so you can see which check fails most per skill.

## Calibration: your examples are the goldens

The rubrics ship with `goldens: []`. They are calibrated against a described bad output (`known_reject`) and the skill's own rules, which is enough to catch invented facts and missing owners. They are not enough to know what **good** looks like for you.

That comes from your examples. Save outputs you actually used, sent or wrote yourself into:

```
morning/examples/<skill>/
```

for example `morning/examples/weekly-update/2026-09-26.md`. Two or three per skill is enough to start. From then on:

- The drafter reads them before writing, so the draft copies your length, structure and voice.
- The verifier grades `ready_to_ship` (and voice checks such as `voice_matches_examples`) against them, so "good" means "like the ones you kept", not "like a template".
- When a draft you approved with no edits comes back, it is a good candidate for the next example. When you correct a draft, the corrected version is a better one.

Examples are yours and live in your workspace. They are never copied into this package.

## Changing a rubric

Draft or change checks from the skill's rules plus your examples, then test both ways: the rubric must **pass** your examples and **fail** the `known_reject`. If it fails a good example or passes the bad one, fix the check, not the example. Keep checks about one thing each, so a fail tells the drafter exactly what to fix.
