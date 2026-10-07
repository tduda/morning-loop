# Confluence (meeting notes pages)

## What it unlocks

Confluence feeds the **meetings** section of your brief: decisions and action items from meeting notes pages your team keeps in Confluence.

Example line: "Planning notes (WEB space, yesterday): 2 action items are yours, 1 decision changed the release date."

## Connect it

Confluence uses the **same** official Atlassian server as Jira. If you already connected Jira, you are done: skip to Prove it works.

```
https://mcp.atlassian.com/v2/mcp
```

Sign in with OAuth. The server sees only what your Atlassian account can see.

### Claude Code

```bash
claude mcp add --transport http atlassian https://mcp.atlassian.com/v2/mcp
```

Start Claude Code, type `/mcp`, pick `atlassian` and sign in. Or turn on the Atlassian connector at claude.ai/customize/connectors; it then appears in Claude Code automatically.

### OpenCode

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

Sign in with `opencode mcp auth atlassian` if the browser does not open on its own.

### Codex CLI

```bash
codex mcp add atlassian --url https://mcp.atlassian.com/v2/mcp
codex mcp login atlassian
```

### API tokens and read-only

API tokens work only if your organization admin has enabled them; see the Jira guide for details. The Atlassian server has no read-only switch, so the loop's own rule applies: nothing is written without your per-item yes.

## Prove it works

Onboarding asks the agent:

> Find the 5 most recently updated Confluence pages in the space I named that look like meeting notes, and list their titles, dates and any action items assigned to me.

**Pass:** pages you recognise and action items that match what you remember. If nothing comes back, check the space key.

## Scope it

You choose:

- **Which space** (by key, for example `WEB`) and, if you can, the **parent page** your meeting notes sit under.
- **How to spot meeting notes.** A title pattern or label, for example titles starting with a date, or the label `meeting-notes`.
- **Mine first.** Whether action items assigned to you come first.

```yaml
sources:
  meetings:
    tool: confluence
    scope: "space WEB, pages under 'Team Meetings', label meeting-notes, updated since the last brief"
    mine_first: true
```

Many teams only put some meetings in Confluence (for example the regular ceremonies). If you also use a notes app, add it as a second meetings source so the brief does not miss the rest.

## Privacy

- **Reads:** pages and comments in the space and parent page you scope.
- **Writes:** never on its own. A drafted page edit or comment waits in your review queue until you say yes to that one item.
- **Stays local:** extracted action items and drafts live in `morning/` on your machine.

## If it fails

1. **"Not authorized".** Your admin may need to allow the Atlassian MCP server for your organization.
2. **Empty results.** The space key is wrong, or the pages are restricted. Open one in your browser to confirm you can see it, then ask the agent to "list Confluence spaces I can see".
3. **It finds the wrong pages.** Tighten `scope` with a parent page or a label.
4. **Sign in expired.** Run the sign in again: `/mcp` (Claude Code), `opencode mcp auth atlassian`, or `codex mcp login atlassian`.

## Sources (checked 2026-10)

- Atlassian Rovo MCP server, getting started: https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/
- API token authentication: https://support.atlassian.com/atlassian-rovo-mcp-server/docs/configuring-authentication-via-api-token/
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
