# Layout: where everything lives

Two places, kept apart on purpose.

## 1. The package (this repo)

Shared code and instructions. You `git pull` it; you never edit it for your own setup.

```
commands/      slash commands: /onboard, /morning, /brief, /tickets, /shipped, /coach
skills/        the drafters and senses, one folder each with SKILL.md
agents/        read-only verifier agents (Claude Code); other clients run the same checks inline
rubrics/       the quality bar each drafter is graded against
stages/        the onboarding stages, one file each: what it costs, what it unlocks, how it is verified
connectors/    one guide per tool: which connector to add, per client, and the test read that proves it works
roles/         role presets that shape the brief
scripts/       the engine: install, setup, doctor, onboarding state, trust layer, delivery, runners
templates/     starter files copied into your workspace
```

## 2. Your workspace

Any folder you already work in (a notes folder, a project folder) or a new one. The loop keeps everything it writes inside **one subfolder, `morning/`**, so it never clutters what you already have.

```
<your folder>/
  morning/
    config.yml              your settings: who you are, which sources are on, your jobs
    profile.md              your role, goals and working rhythm, in your words (stage 1)
    briefs/                 one brief per day: YYYY-MM-DD.md, and briefs/rendered/ for the HTML
    drafts/YYYY-MM-DD/      what the loop drafted that day, plus .trust/ (verdicts) and questions.md
    notes/                  meeting notes the loop wrote or read
    examples/<skill>/       2 or 3 of YOUR past examples per drafter: they set the voice and the quality bar
    state/
      onboarding.json       which stages are done, skipped or pending
      ledger.md             your commitments: what you owe, what others owe you, what's coming
      run-log.md            one line per run, honest about what was automatic
      receipts/             did today's brief actually reach you
      brief-index.json      brief numbers
      outbound-ledger.md    everything that left your machine under your name
      provenance.jsonl      where each action came from
      coach/                your coaching plan and history
      runner.log            the scheduled runner's log
      triage-log.md         what inbox-triage ranked, so tomorrow can tell new from repeated
    engine -> <package>/scripts   (a link; a copy on systems without links)
```

Every script finds the workspace by walking up from the folder you run it in until it finds `morning/state/`. Run the loop from your folder (or anywhere inside it), never from the package.

## Path names used by the engine

| what | path (relative to your folder) |
|---|---|
| config | `morning/config.yml` |
| brief | `morning/briefs/{DATE}.md` |
| rendered brief | `morning/briefs/rendered/brief-{DATE}.html` |
| drafts | `morning/drafts/{DATE}/` |
| review packet | `morning/drafts/{DATE}/review-packet.md` |
| questions | `morning/drafts/{DATE}/questions.md` |
| meeting actions | `morning/drafts/{DATE}/meeting-actions.md` |
| trust stamps | `morning/drafts/{DATE}/.trust/` |
| commitments ledger | `morning/state/ledger.md` |
| run log | `morning/state/run-log.md` |
| receipts | `morning/state/receipts/{DATE}.json` |
| brief index | `morning/state/brief-index.json` |
| outbound ledger | `morning/state/outbound-ledger.md` (+ `.jsonl`) |
| provenance | `morning/state/provenance.jsonl` |
| coaching | `morning/state/coach/` |
| onboarding state | `morning/state/onboarding.json` |
| runner log | `morning/state/runner.log` |
| meeting notes | `morning/notes/` |
| engine | `morning/engine/` |
