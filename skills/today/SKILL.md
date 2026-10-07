---
name: today
description: "Reads whichever sources config.yml has switched on (tasks, calendar, meetings, inbox, chat, metrics) plus profile, goals and the ledger, and returns typed findings (claim, source excerpt, timestamp) for /morning to plan from. Use as the daily sense step of /morning, or on \"what's on today\", \"sense my day\". Works with zero sources on."
---

# today: the daily sense step

This skill reads. It does not plan, rank, draft or send. Its only output is a list of typed findings that /morning plans from and the verifier checks. If a finding cannot quote its source, it is not a finding.

## Inputs

| input | where | required |
|---|---|---|
| owner, role, timezone | `morning/config.yml` (`owner.*`) | yes |
| profile and goals | `morning/profile.md` | yes (may be thin) |
| commitments | `morning/state/ledger.md` | yes (may be empty) |
| yesterday's brief | `morning/briefs/{YESTERDAY}.md` | no |
| sources | `morning/config.yml` `sources.<name>.enabled` for `tasks`, `calendar`, `meetings`, `inbox`, `chat`, `metrics` | each optional |

Read the clock once at the start (`date`) and use that value everywhere. Never estimate a time.

## Steps

1. **Load the always-on context.** Profile, goals and ledger. These three alone are enough to produce a brief, so a run with every source off is a normal run, not a failure.
2. **List the sources that are on.** For each one switched on in config, check the connector answers with one cheap read (the test read in `connectors/<tool>.md`). A source that is on but does not answer is `unavailable`, with the error, and the run continues.
3. **Read each available source, one bounded read each.** Dispatch one sense-probe per source where the client supports subagents; otherwise read them inline, one at a time.
   - `tasks`: open items assigned to the owner, items they are waiting on, and anything that changed status since the last run. Use the scope filter in config, never a project prefix alone, since projects are often shared.
   - `calendar`: today and tomorrow, with attendees and description.
   - `meetings`: notes or transcripts new since the last run. Record whether each is a transcript (verbatim) or a summary (paraphrase).
   - `inbox` and `chat`: unread plus the last 24 hours (72 on a Monday). Read only; never mark read.
   - `metrics`: hand off to `metrics-pulse` if it is on; do not read metrics here.
4. **Read the ledger against today.** Every open line due today, overdue, or due tomorrow becomes a `commitment` finding. A promise with no date stays a finding with `due: none`.
5. **Write findings.** One per claim, in the schema below. Do not merge findings from two sources into one claim.
6. **Write the source table** at the top of the output: every source in config, with `read`, `off`, or `unavailable: <reason>`.

## Finding schema

```yaml
- id: f-{source}-{n}          # stable within the run, e.g. f-tasks-3
  type: status | number | change | absence | commitment | event | ask
  claim: "one line, plain words"
  source: tasks | calendar | meetings | inbox | chat | metrics | profile | goals | ledger
  ref: "the object id, URL, query or file path actually read"
  excerpt: "verbatim text from the source that contains what the claim asserts"
  observed_at: "when the source says it happened (ISO 8601), or null"
  read_at: "when this run read it (ISO 8601, from the clock)"
  verbatim: true              # false when the source is a summary or paraphrase
  gated: true                 # true for status, number, change, absence: verify before use
```

Type guide: `status` (where something is now), `number` (a count or metric), `change` (moved since last run), `absence` (something expected is not there; name the query that would have found it), `commitment` (owed by or to the owner), `event` (a meeting or deadline), `ask` (someone is waiting on the owner).

## Output

```markdown
# Sense {DATE} (read at {HH:MM} {TZ})

## Sources
| source | state | note |
|---|---|---|
| profile | read | |
| ledger | read | 4 open, 1 overdue |
| calendar | off | |
| tasks | unavailable | connector returned 401 |

## Findings
{the YAML list}

## Not checked
{anything the plan will expect that this run did not read, and why}
```

Write it to `morning/drafts/{DATE}/sense.md`.

## Never

- Never fill a slot from memory or a previous brief. Yesterday's brief is context for `change` findings only, and a claim taken from it is re-read live or dropped.
- Never paraphrase into `excerpt`. If you cannot quote, the finding is `unavailable`, not softened.
- Never call something absent after one query. An `absence` finding names the query, the scope, and any second place it could live.
- Never write to a source (no mark-read, no status change, no reply).
- Never rank, prioritise or recommend. That is /morning's job.
- Never use today's partial data as a trend.

## Degrading

| situation | what happens |
|---|---|
| zero sources on | findings come from profile, goals and ledger only; source table says so; brief still runs |
| a source on but down | `unavailable` row with the error; no findings invented for it |
| ledger empty | one line: "ledger empty"; not an error |
| profile thin | proceed, and add one `ask` finding: "profile has no goals yet" |
| meeting source is summary-only | findings carry `verbatim: false`; downstream skills treat them as paraphrase |
