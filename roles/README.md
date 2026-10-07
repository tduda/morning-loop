# Role presets

These presets shape the brief to the person running it. Set `owner.role_profile` in your config to one of the file names below (without `.yml`), or pass choose it in onboarding stage 1.

Each preset decides four things:

- **lens:** what the brief leads with, and what "top of your list" means for this role
- **sections:** which brief sections run, and which stay off because they'd be noise for this role
- **senses:** which sources the loop reads first
- **suggested jobs:** the jobs drafted for you, using only skills that ship in this package. Jobs a role has but no shipped skill can do are listed as **gaps**, commented out, so your config never claims coverage it doesn't have.

A preset is a starting point. After your first week, `/jtbd-capture` reads your own setup and adjusts routing to the jobs you really do. What a preset can't do is invent the quality bar for a job: a drafter is only trustworthy with a rubric and real examples, and those come from you.

| preset | for |
|---|---|
| `product-owner` | POs and PMs: sprint goal, quarterly goals, stakeholders, decisions |
| `engineer` | developers: your tickets, reviews, blockers, kickoffs |
| `scrum-master` | SMs: ceremonies, sprint health, stalls, the board |
| `designer` | designers: design tickets, feedback loops, handoffs |
| `community-manager` | CM: launches to communicate, community threads, FAQs |
| `data-analyst` | analysts: data requests, experiment readouts, metric health |
| `supporter` | support: escalations, product changes to brief, known issues |
