---
id: schedule
n: 5
title: Make it automatic
minutes: 5
optional: false
unlocks: "the loop runs itself: the brief is waiting when you open your laptop, with nothing to type"
brief_sample: |
  (a notification at 07:52, or the first time you open your laptop that morning)
  ☀️ Morning Brief #12 · 2 to review · 1 question · 4 for you
  "Pricing page copy is waiting on you, and the review is at 11:00."
---
## Why this stage can't be skipped
This is the stage that turns Morning Loop from a command you have to remember into a loop that runs itself. Without it, nothing happens unless you type /morning, and a brief you have to ask for is just another chore. Every other tool stage is optional; this one is what makes the rest pay off. If they want to skip it, say exactly that, and offer to do it right after stage 1 instead of at the end: it takes 5 minutes and works with zero tools connected.

## Be clear first
The brief is made **on their computer**, so it arrives when the computer is on: at the scheduled time, or the first time they open it that morning (the catch-up keeps trying until 12:00). A laptop that stays shut all morning gets no brief that day.

## What we do
Follow `docs/SCHEDULE.md` for their system: macOS (two launchd jobs: the scheduled run and the catch-up), Windows (two Task Scheduler tasks), Linux (cron). Run the runner once by hand first; only then load the schedule.

## Prove it works
The supervised run produces today's brief and a receipt with status `sent` (or `rendered_not_sent` on the file channel). The schedule lists exactly two entries. Set `schedule.enabled: true`.

## Tell them
"From tomorrow the brief makes itself. If it ever doesn't arrive, the next one says why. Next, when you have a week of briefs: your recurring jobs, so the loop starts drafting work for you (20 minutes)."
