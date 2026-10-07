---
id: tasks
n: 2
title: Your task tracker
minutes: 10
optional: true
revisit_when: "the user keeps adding work items to their commitments by hand, or mentions tickets, issues or a board"
unlocks: "what's assigned to you, what's stuck, and what changed since yesterday"
brief_sample: |
  ── YOUR WORK ── 7 open · 2 need you today
  - Pricing page copy · In review for 4 days, waiting on you [V]
  - Billing export bug · moved to Blocked yesterday by Sam: needs a decision on scope [V]
  ── STUCK ── 1 item with no movement for 6 days: Onboarding email audit (owner: you). Next action: split or drop.
---
## What we ask
Which tracker: Jira, Linear, GitHub issues, or Notion. If none, skip this stage.

## Connect
Follow `connectors/<tool>.md` for their client. Prefer read-only access.

## Scope
Ask what counts as theirs: a project, a team, a set of repos, a database. Mine-first stays on unless they ask otherwise. A shared project needs a scope, or other teams' work leaks into the brief.

## Prove it works
The guide's test read must return real items they recognise. Show the five most recent items assigned to them and ask: "Are these yours?" Only on a yes, set `sources.tasks.enabled: true` with `tool` and `scope`.

## Tell them
"Your brief now leads with what's on your plate, flags what's stuck and names the next action. Next: calendar and meeting notes, for prep and follow-ups (10 minutes)."
