---
id: inbox_chat
n: 4
title: Inbox and chat
minutes: 10
optional: true
revisit_when: "the user added commitments like 'reply to ...' or 'get back to ...', or mentions email or chat threads"
unlocks: "who's waiting on a reply from you, and the promises you made in threads, tracked"
brief_sample: |
  ── NEEDS YOUR REPLY ── 3
  - Sam (Slack, #team-product, yesterday 16:40): is the pricing copy final? You're the last approver.
  - Finance (email, 2 days): invoice question, blocks their month-end
  ── YOU PROMISED ── "I'll send the deck Friday" (Slack, Tuesday) → added to your list, due Friday
---
## What we ask
1. Email: Gmail or Outlook.
2. Chat: Slack, Teams or Mattermost, and which channels matter. Mentions and direct messages are always read.

## Connect
`connectors/<tool>.md`. Read-only scopes. The loop never sends a message or email; drafting a reply is fine, sending needs their yes every time.

## Prove it works
Show the three most recent messages that mention them; they confirm. Then enable `sources.inbox` / `sources.chat` and add job `inbox_triage` (when: daily, skill: inbox-triage, output: auto).

## Tell them
"Nobody waits on you without the brief saying so, and your own 'I'll do X' lines become reminders. Next: make it automatic, so the brief is ready when you open your laptop (5 minutes)."
