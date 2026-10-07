---
id: calendar_meetings
n: 3
title: Calendar and meeting notes
minutes: 10
optional: true
revisit_when: "commitments or notes mention meetings, prep, or follow-ups from a meeting"
unlocks: "prep for today's meetings, and yesterday's action items pulled into your list"
brief_sample: |
  ── MEETINGS TODAY ── 3
  - 11:00 Roadmap review · prep ready: 2 decisions needed, 1 open item of yours with Jordan
  - 15:00 1:1 with Sam · last time you promised the hiring plan; it's still open
  ── FROM YESTERDAY'S MEETINGS ── 2 actions added to your list, 1 draft task waiting for your tick
---
## What we ask
1. Calendar: Google or Outlook.
2. Meeting notes, if any: Granola, Confluence, Notion, or a folder of notes. Skip if they don't keep notes.

## Connect
`connectors/<tool>.md` for each. A notes folder needs no connector, just the path.

## Prove it works
Calendar: list today's and tomorrow's meetings; they confirm. Notes: open the most recent note and show its title and date. Only then enable `sources.calendar` and `sources.meetings`, and add jobs `meeting_prep` (when: calendar, skill: meeting-prep, output: draft) and `meeting_debrief` (when: meeting_new, skill: meeting-debrief, output: draft).

## Be honest about notes
Summary-style notes (most AI note-takers) are paraphrase. Tasks drafted from them come as one-line stubs ("confirm scope with Sam"), never with invented details.

## Tell them
"Meetings now come with prep, and what you agreed in them doesn't get lost. Next: inbox and chat, so the brief tells you who's waiting on you (10 minutes)."
