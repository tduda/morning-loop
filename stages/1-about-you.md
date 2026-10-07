---
id: about_you
n: 1
title: About you
minutes: 10
optional: false
unlocks: "a brief every morning built on your goals, and a commitments list you add to just by talking"
brief_sample: |
  ── TODAY ── Thursday · focus: ship the pricing page draft (goal 1)
  ── YOUR COMMITMENTS ── 3 open
  - Send the vendor comparison to Sam · you said Tuesday · due today
  - Review Jordan's proposal · added yesterday
  ── COACHING ── You've carried "book the 1:1s" for 4 days. In your control: one calendar invite. Today: send it before lunch.
---
## What we ask (keep it to these; everything else can wait)
1. Name, and role in your own words.
2. Timezone and when your workday usually starts.
3. Your top 3 goals for this quarter or the next few weeks, one line each.
4. Your recurring meetings (name, how often, your part in it). Rough is fine.
5. Who you report to, and who depends on you most.
6. Optional: pick a role preset from roles/README.md, or leave it general.

If they already have notes that answer these (a profile, a goals doc, a README), read them first and only ask about what's missing.

## What we write
- `morning/profile.md`: answers 1, 4, 5 in their words.
- `morning/goals.md`: the goals, numbered.
- config `owner.*` and `role_profile`.
- `morning/state/coach/plan.md`: one starter thread drawn from what they said matters.

## Prove it works
Run `/morning` once now. The brief must show their goals as the day's focus and an empty commitments list with "add one by saying: remind me to ...". Add one commitment together so they see it land.

## Tell them
"Tomorrow morning, type /morning and you get a brief built on your goals, even with nothing connected (stage 5 makes it appear on its own). Say 'remind me to...' or 'I promised X to Y by Friday' any time and it lands in your list. Next: your task tracker, so the brief knows what's actually on your plate (10 minutes)."
