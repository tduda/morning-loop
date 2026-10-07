---
id: metrics
n: 7
title: Metrics
minutes: 10
optional: true
revisit_when: "goals or commitments mention a number, a metric, a dashboard or an experiment"
unlocks: "a daily pulse on the numbers you choose, with the window and source next to every figure"
brief_sample: |
  ── PULSE ── last 7 complete days vs the 7 before
  - Signups: 1,240 a day vs 1,180 (+5%) [V]
  - Activation (day 1): 31.2% vs 32.0%, within normal range [V]
---
## What we ask
Which analytics tool (Amplitude, GA4, Mixpanel, PostHog), which project(s), and which 2 to 5 metrics matter to them.

## Connect
`connectors/<tool>.md` if a guide exists; otherwise the tool's official MCP server, verified with one read.

## Prove it works
Read one pinned metric for the last 7 complete days and show it with its window and source; they confirm it matches what they'd see in the tool. Enable `sources.metrics` with `projects` and `pinned`, and add job `metrics_pulse` (when: daily, skill: metrics-pulse, output: auto).

## Rules the pulse keeps
Never today's partial day. Never an estimated number: "not checked" is a valid answer. Never call something absent on one project when several are configured.
