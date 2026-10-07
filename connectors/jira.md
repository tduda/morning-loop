# Jira

## What it unlocks

Jira feeds the **tasks** section of your brief: what is assigned to you, what changed since yesterday, and what has sat still too long.

Example line: "WEB board: 3 issues assigned to you are in progress, 1 has had no update for 6 days (the login timeout bug)."

## Connect it

Use Atlassian's official remote server (the Atlassian Rovo MCP server). One connection covers both Jira and Confluence. The current endpoint is:

```
https://mcp.atlassian.com/v2/mcp
```

Sign in with OAuth: a browser window opens, you log in to Atlassian and approve access. The server only ever sees what your own Atlassian account can see.

### Claude Code

```bash
claude mcp add --transport http atlassian https://mcp.atlassian.com/v2/mcp
```

Start Claude Code, type `/mcp`, pick `atlassian` and sign in.

If you use claude.ai, you can instead turn on the Atlassian connector at claude.ai/customize/connectors. It then appears in Claude Code automatically (you will see it in `/mcp`).

### OpenCode

Add this to `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "atlassian": {
      "type": "remote",
      "url": "https://mcp.atlassian.com/v2/mcp",
      "enabled": true
    }
  }
}
```

OpenCode starts the sign in on first use. To run it by hand: `opencode mcp auth atlassian`.

### Codex CLI

```bash
codex mcp add atlassian --url https://mcp.atlassian.com/v2/mcp
codex mcp login atlassian
```

Or add it to `~/.codex/config.toml` yourself:

```toml
[mcp_servers.atlassian]
url = "https://mcp.atlassian.com/v2/mcp"
```

### API token instead of OAuth (optional)

Atlassian also supports API tokens, but only if your organization admin has turned this on. You create a personal token at https://id.atlassian.com/manage-profile/security/api-tokens and pick its scopes there. Choose read scopes only. The token goes in an `Authorization` header as `Basic <base64 of your-email:token>`. Some tools are not available with tokens. Details: check the current docs at https://support.atlassian.com/atlassian-rovo-mcp-server/docs/configuring-authentication-via-api-token/

### Read-only

The Atlassian server has no read-only switch. OAuth gives the agent the same rights you have. The loop itself never writes to Jira without your per-item yes (see Privacy).

## Prove it works

Onboarding asks the agent:

> List the 5 most recently updated Jira issues assigned to me, with key, title, status and last updated date.

**Pass:** you see up to 5 real issues you recognise, newest first. Zero issues is only a pass if you truly have nothing assigned; otherwise check the site and project you picked.

## Scope it

You choose:

- **Which site** (if you have more than one Atlassian site).
- **Which projects or board.** Write it as a JQL fragment, for example `project = WEB`.
- **Mine first.** Whether your own issues lead the section before the wider project view.

```yaml
sources:
  tasks:
    tool: jira
    scope: "project = WEB AND statusCategory != Done"
    mine_first: true
```

If your Jira project is shared with other teams, narrow it with a team field, component or label in the JQL fragment, so the brief only shows your team's work.

## Privacy

- **Reads:** issues, statuses, comments and sprint data in the scope you set.
- **Writes:** never on its own. A drafted comment or ticket waits in your review queue, and nothing is sent to Jira until you say yes to that one item.
- **Stays local:** the brief, drafts and logs live in `morning/` on your machine. Your agent client (and its model provider) sees the issues it reads while it writes the brief.

## If it fails

1. **The sign in window never opens.** In Claude Code run `/mcp` and choose the server again. In OpenCode run `opencode mcp auth atlassian`. In Codex run `codex mcp login atlassian`.
2. **"Not authorized" or an empty site list.** Your admin may have to allow the Atlassian MCP server or AI access for your organization. Ask them, and share the getting started link below.
3. **Zero issues, but you know you have some.** You probably picked the wrong site, or the JQL fragment has a typo. Ask the agent to "list my visible Jira projects" and fix the `scope`.
4. **It worked yesterday, now it fails.** OAuth sessions expire. Sign in again with the same command as in point 1.
5. **You set up the older `/v1/sse` URL from another guide.** Replace it with `https://mcp.atlassian.com/v2/mcp`.

## Sources (checked 2026-10)

- Atlassian Rovo MCP server, getting started: https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/
- API token authentication: https://support.atlassian.com/atlassian-rovo-mcp-server/docs/configuring-authentication-via-api-token/
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
