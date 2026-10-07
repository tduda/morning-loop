---
name: metrics-pulse
description: "Optional. Reads the metrics the user pinned in config (metrics.pinned) from their analytics connector and compares the last 7 complete days with the 7 before, never including today and never estimating. \"Not checked\" is a valid answer. Use on \"how are my numbers\", \"metrics pulse\", or as the metrics step of /morning when the metrics source is on."
---

# metrics-pulse: pinned numbers, honestly read

A short read of a few numbers the user chose. A wrong number does more damage than a missing one, so this skill would rather say "not checked" than guess.

## Inputs

| input | where | required |
|---|---|---|
| pinned metrics | config `metrics.pinned`: each with `name`, `query` (saved chart id, event, or query text), optional `direction` (up_is_good or down_is_good), optional `alert_pct` | yes |
| connector | config `sources.metrics` (the analytics tool and its connection) | yes |
| timezone | config `owner.timezone` | yes |

## Window

- Read the clock. Today is excluded, always: a partial day makes every metric look like it fell.
- **Current window:** the 7 complete days ending yesterday.
- **Prior window:** the 7 complete days before that.
- Use daily granularity and sum the days yourself. Weekly or monthly buckets may not respect the window edges.
- For any metric that matures over time (retention, conversion with a long window), check that the latest days are complete. If they are not, shift both windows back until they are, and say so.

## Steps

1. **Check the connector** with one cheap read. If it fails, every metric is `not checked: {error}` and the skill stops.
2. **For each pinned metric,** run its query for both windows with the same definition, filters and timezone.
3. **Compute** current total, prior total, and change as a percent of prior. If prior is zero, show the change as `n/a (prior 0)`.
4. **Flag** only when the change passes `alert_pct` (default 15) in the bad direction. If `direction` is not set, flag in either direction and do not call it good or bad.
5. **Record provenance** for each number: the query or chart id, the window dates, and when it was read.
6. **Emit findings** for /morning in the `today` finding schema, type `number`, `gated: true`.

## Output

Write to `morning/drafts/{DATE}/metrics-pulse.md`.

```markdown
# Metrics {DATE}
Window: {start} to {end} vs {prior start} to {prior end} (complete days, {timezone}). Today excluded.

| metric | last 7d | prior 7d | change | flag | source |
|---|---|---|---|---|---|
| {name} | {value} | {value} | {+x.x%} | {flag or blank} | {query or chart id, read at HH:MM} |
| {name} | not checked | | | | {reason} |

{one line per flagged metric: what moved, by how much, and one question worth asking. No cause is asserted.}
```

## Never

- Never include today.
- Never estimate, interpolate, extrapolate or round to make a number read better. No reading, no number.
- Never call a metric absent or zero on one failed query. Say `not checked` with the reason.
- Never explain a movement as fact. Offer a question to check, not a cause.
- Never compare windows of different lengths, or a partial window with a full one.
- Never add metrics the user did not pin.

## Degrading

| situation | effect |
|---|---|
| metrics source off | skill does not run; brief has no metrics section |
| connector down | every row `not checked`, with the error |
| one query fails | that row `not checked`; the others still report |
| `metrics.pinned` empty | report "no metrics pinned" once; suggest pinning one or two |
| data not mature | windows shifted back, and the header says by how many days |
