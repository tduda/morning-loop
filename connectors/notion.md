# Notion (tasks databases and docs)

## What it unlocks

Notion feeds the **tasks** section of your brief: rows from your tasks database that are due, overdue or assigned to you, plus docs that changed since yesterday.

Example line: "Team Tasks database: 2 items due today, 1 overdue (draft the pricing page copy). The Product Roadmap doc was edited yesterday."

## Connect it

Use Notion's official hosted server:

```
https://mcp.notion.com/mcp
```

(A fallback for older clients: `https://mcp.notion.com/sse`.)

Notion's hosted server **only supports OAuth**. A browser window opens, you log in to Notion and approve access. There is no API-token option for the hosted server, and no read-only switch: the agent can see what your Notion account can see.

### Claude Code

```bash
claude mcp add --transport http notion https://mcp.notion.com/mcp
```

Start Claude Code, type `/mcp`, pick `notion` and sign in.

Or turn on the Notion connector at claude.ai/customize/connectors. It then appears in Claude Code automatically.

### OpenCode

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "notion": {
      "type": "remote",
      "url": "https://mcp.notion.com/mcp",
      "enabled": true
    }
  }
}
```

OpenCode starts the sign in on first use. To run it by hand: `opencode mcp auth notion`.

### Codex CLI

In `~/.codex/config.toml`:

```toml
[mcp_servers.notion]
url = "https://mcp.notion.com/mcp"
```

Then sign in:

```bash
codex mcp login notion
```

## Prove it works

Onboarding asks the agent:

> Find my tasks database in Notion and list 5 items that are assigned to me or due soonest, with title, status and due date.

**Pass:** up to 5 real rows you recognise. If the agent cannot find the database, give it the database name or link.

## Scope it

You choose:

- **Which database** holds your tasks (its name or link), and which property means "assigned to me" and "due".
- **Which docs or teamspace** to watch for changes, if any.
- **Mine first.** Whether your own rows lead the section.

```yaml
sources:
  tasks:
    tool: notion
    scope: "database 'Team Tasks': Assignee = me, Status not Done, sort by Due; watch teamspace 'Product' for edits"
    mine_first: true
```

## Privacy

- **Reads:** the databases and pages you scope, within what your Notion account can access.
- **Writes:** never on its own. Status changes or new pages wait in your review queue until you say yes to that one item.
- **Stays local:** the brief, drafts and logs live in `morning/` on your machine. Workspace owners can see and revoke the connection in Notion under Settings, Connections.

## If it fails

1. **Sign in fails or loops.** Claude Code: `/mcp` and sign in again. OpenCode: `opencode mcp auth notion`. Codex: `codex mcp login notion`.
2. **The agent cannot find your database.** Check that your own account can open it in Notion. Then put its exact name or link in `scope`.
3. **"Not allowed" in a company workspace.** A workspace owner may have restricted MCP connections. Ask them to allow it under Settings, Connections.
4. **Your client cannot do remote OAuth.** Notion documents a fallback: run `npx -y mcp-remote https://mcp.notion.com/mcp` as a local command server.

## Sources (checked 2026-10)

- Notion MCP overview: https://developers.notion.com/docs/mcp
- Connect an MCP client: https://developers.notion.com/guides/mcp/get-started-with-mcp
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
