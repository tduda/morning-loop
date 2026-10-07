---
id: recurring_jobs
n: 6
title: Your recurring jobs
minutes: 20
optional: true
recommended_after_days: 5
revisit_when: "5 or more briefs exist, or the user mentions a report, update or prep they write every week"
unlocks: "drafts of your recurring work (weekly update, meeting prep, follow-ups), checked against a quality bar, sent only with your yes"
brief_sample: |
  ── READY FOR YOUR REVIEW ── 2
  - [ ] Weekly update for your manager · READY (passed 9 of 9 checks) · drafts/2026-10-09/weekly-update.md
  - [ ] Prep: Roadmap review · NEEDS EDIT: one claim couldn't be verified (named in the draft)
---
## Best after a week
With five or more briefs, the interview starts from what the loop has already seen instead of a blank page. It still works on day 1.

## What we do
Run the `jobs-interview` skill. It drafts their recurring jobs from profile.md, the ledger and recent briefs, asks only about gaps, grades each honestly, and proposes `jobs:` rules. Jobs with no shipped skill are written commented out, with the reason.

## Set expectations honestly
A drafter gets good when it has a few real examples of the user's own work. Ask them to drop 2 or 3 past examples into `morning/examples/<skill>/`. Until then, expect NEEDS EDIT more often than READY.

## Prove it works
Run the first job by hand. The draft lands in `morning/drafts/<today>/` with a verdict at the top. Nothing is sent.

## Tell them
"The loop now drafts your recurring work. You review and ship; nothing leaves without your yes. After a week, the feedback prompt asks what saved you time."
