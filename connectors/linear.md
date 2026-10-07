# Linear

## What it unlocks

Linear feeds the **tasks** section of your brief: issues assigned to you, how the current cycle is going, and anything blocked or overdue.

Example line: "WEB team, current cycle: 4 of your 7 issues are done, 1 is blocked waiting on design."

## Connect it

Use Linear's official remote server. Linear also offers a **read-only endpoint** that only ever exposes read tools. The loop only needs to read, so use that one:

```
https://mcp.linear.app/mcp/readonly
```

(The full endpoint, with write tools, is `https://mcp.linear.app/mcp`.)

Sign in with OAuth: a browser window opens, you log in to Linear and approve access. Linear also accepts an API key or bearer token in an `Authorization: Bearer <key>` header if you prefer that.

### Claude Code

```bash
claude mcp add --transport http linear https://mcp.linear.app/mcp/readonly
```

Start Claude Code, type `/mcp`, pick `linear` and sign in.

If you use claude.ai, you can turn on the Linear connector at claude.ai/customize/connectors instead. It then shows up in Claude Code automatically. Note that the claude.ai connector may include write tools.

### OpenCode

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "linear": {
      "type": "remote",
      "url": "https://mcp.linear.app/mcp/readonly",
      "enabled": true
    }
  }
}
```

OpenCode starts the sign in on first use. To run it by hand: `opencode mcp auth linear`.

Linear's docs also describe a fallback for clients that cannot do remote OAuth: run `npx -y mcp-remote https://mcp.linear.app/mcp` as a local command. You should not need it with OpenCode.

### Codex CLI

```bash
codex mcp add linear --url https://mcp.linear.app/mcp/readonly
codex mcp login linear
```

Or in `~/.codex/config.toml`:

```toml
[mcp_servers.linear]
url = "https://mcp.linear.app/mcp/readonly"
```

Linear's docs say Codex needs this if it is your first MCP server with OAuth:

```toml
[features]
experimental_use_rmcp_client = true
```

## Prove it works

Onboarding asks the agent:

> List the 5 most recently updated Linear issues assigned to me, with identifier, title, status and team.

**Pass:** up to 5 real issues you recognise, newest first.

## Scope it

You choose:

- **Which team or teams**, by team key (for example `WEB`).
- **Cycle or project.** Whether the brief follows the current cycle, a project, or everything open.
- **Mine first.** Whether your own issues come before the team view.

```yaml
sources:
  tasks:
    tool: linear
    scope: "team WEB, current cycle, not completed or canceled"
    mine_first: true
```

## Privacy

- **Reads:** issues, statuses, cycles, projects and comments in the teams you scoped.
- **Writes:** none through the read-only endpoint. Even with the full endpoint, the loop never writes without your per-item yes.
- **Stays local:** the brief, drafts and logs live in `morning/` on your machine. Your agent client (and its model provider) sees the issues it reads while it writes the brief.

## If it fails

1. **Sign in never completes.** Claude Code: `/mcp`, pick `linear`, sign in again. OpenCode: `opencode mcp auth linear`. Codex: `codex mcp login linear`.
2. **Codex says OAuth is not supported.** Update Codex, then add the `[features]` flag shown above.
3. **On Windows with WSL the connection drops.** Linear's docs suggest the SSE fallback, `https://mcp.linear.app/sse`, through `mcp-remote` with `--transport sse-only`. Check the current docs for the exact lines.
4. **No issues come back.** Check the team key in `scope`. Ask the agent to "list my Linear teams" and copy the key exactly.
5. **The agent tries to update an issue and fails.** That is the read-only endpoint doing its job. Updates go through your review queue instead.

## Sources (checked 2026-10)

- Linear MCP server: https://linear.app/docs/mcp
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
