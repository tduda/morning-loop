# Granola

## What it unlocks

Granola feeds the **meetings** section of your brief: decisions and action items from yesterday's meetings, and anything you promised someone.

Example line: "From yesterday's design sync: you said you would send the test plan by Wednesday. Nobody owns the open question about the pricing copy."

## Connect it

Use Granola's official hosted server:

```
https://mcp.granola.ai/mcp
```

It uses OAuth (a browser window opens, you log in to Granola). No API key is needed.

What you can read depends on your Granola plan. On the free Basic plan you get your own notes from the last 30 days only, without folder, search or transcript tools. Paid plans add transcripts and more. Check your plan in Sources.

### Claude Code

```bash
claude mcp add granola --transport http https://mcp.granola.ai/mcp
```

Start Claude Code, type `/mcp`, pick `granola` and choose Authenticate.

Or connect Granola at claude.ai/customize/connectors. It then shows up in Claude Code automatically.

### OpenCode

Granola documents that any client with remote (Streamable HTTP) and OAuth support can use the URL. In `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "granola": {
      "type": "remote",
      "url": "https://mcp.granola.ai/mcp",
      "enabled": true
    }
  }
}
```

Sign in with `opencode mcp auth granola` if the browser does not open on its own.

### Codex CLI

```bash
codex mcp add granola --url https://mcp.granola.ai/mcp
codex mcp login granola
```

Or in `~/.codex/config.toml`:

```toml
[mcp_servers.granola]
url = "https://mcp.granola.ai/mcp"
```

Granola's own docs only give exact steps for Claude, ChatGPT and Claude Code. The OpenCode and Codex lines above follow each client's standard setup for a remote OAuth server.

### Read-only

The Granola server is for reading notes. The loop does not write to Granola.

## Prove it works

Onboarding asks the agent:

> List my 5 most recent Granola meetings with date and title, and give the action items from the latest one.

**Pass:** meetings you recognise, newest first, and action items that match what you remember. Treat the notes as summaries, not exact quotes.

## Scope it

You choose:

- **Which meetings.** All of them, or only certain folders (folders need a paid plan).
- **How far back.** Usually yesterday plus anything since the last brief.
- **Mine first.** Whether action items owned by you come first.

```yaml
sources:
  meetings:
    tool: granola
    scope: "my meetings since the last brief; folders: Product, 1:1s"
    mine_first: true
```

## Privacy

- **Reads:** meeting notes (and transcripts, if your plan includes them) in the scope you set.
- **Writes:** none to Granola. Action items become entries in your local ledger. Tickets or follow ups drafted from a meeting wait in your review queue until you say yes to each one.
- **Stays local:** extracted action items and drafts live in `morning/` on your machine. Meeting notes summarise what people said; the loop never presents them as exact quotes.

## If it fails

1. **Sign in does not finish.** Claude Code: `/mcp`, pick `granola`, Authenticate. OpenCode: `opencode mcp auth granola`. Codex: `codex mcp login granola`.
2. **Only the last 30 days show, or transcript tools are missing.** That is the free plan limit. Upgrade, or accept the shorter window.
3. **"Rate limited".** Granola allows about 100 requests a minute across all tools. Wait a minute and run again, or narrow the scope.
4. **A meeting is missing.** Check it exists in the Granola app and has finished processing.

## Sources (checked 2026-10)

- Granola MCP: https://docs.granola.ai/help-center/sharing/integrations/mcp
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
