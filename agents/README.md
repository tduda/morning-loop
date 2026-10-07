# Subagent definitions

Four named agents that move the morning loop's quality contract out of prose and into
structure. Before these existed, `morning.md` described each role in the prompt and
spawned the default general-purpose subagent, which meant a verifier inherited `Write`,
`sense.probe_model_cheap: haiku` was a suggestion the orchestrator had to remember, and
`quality.verifier_is_independent: true` was a promise rather than a property. It failed
on 2026-08-26 and a full two-verifier rubric grid had to be retracted.

| File | Model | Can write files? | Role |
|---|---|---|---|
| `claim-verifier.md` | sonnet | **No** | Re-runs one gated claim against its live source. Kills it or passes it. |
| `disagreement-judge.md` | opus | **No** | Rules per disputed check when two verifiers disagree. Ties break toward FAIL. |
| `sense-probe.md` | haiku | **No** | One bounded extraction: a JQL, a chart, an inbox, a page. Returns claim + verbatim excerpt or `unavailable`. |
| `job-drafter.md` | inherited | Yes | Runs a skill and writes one draft to `morning/drafts/{DATE}/`. Forbidden from grading itself or shipping. |

The read-only three have no `Write` or `Edit` in their `tools:` line. That is the point:
a verifier that cannot edit the artifact it grades is a property of the toolset, not a
rule it might drift from.

## The gotcha that will bite you

**Definitions are read at SESSION START.** Adding, renaming, or (assume) editing one
does not register it in a session already running. The call fails with:

```
agent type 'claim-verifier' not found. Available agents: claude, claude-code-guide,
Explore, general-purpose, Plan, statusline-setup
```

This cost `workflows/ship-triage.mjs` its entire verify phase on 2026-09-01: eight
agents errored while the six triage agents on the default type succeeded. **Restart the
session after touching anything in here.**

For anything long-lived that might run in either state, try the custom `agentType` and
catch `not found` to fall back to the default type with the rules inlined, then label
the result as the weaker path. `ship-triage.mjs` has a worked example. A fallback that
reports itself as the real agent is the same over-claim this workspace keeps retracting.

## Using them

```js
Agent({ subagent_type: "claim-verifier", prompt: "..." })      // in conversation
agent(prompt, { agentType: "claim-verifier", schema: ... })     // in a workflow
```

The agent id lands in the transcript automatically, which is what makes a stamp naming
its verifiers checkable rather than a matter of trust. That was the candidate fix the
run log proposed on 2026-08-26 and it is now available.
