# Connectors

Each guide here connects one tool to the loop. Every guide has the same six parts: what it unlocks, how to connect it in your client, one test read that proves it works, how to scope it, what the loop reads, and what to do if it fails.

You do not need all of them. Onboarding asks about one stage at a time, and each stage works with a single tool. Most people connect one task tool, one calendar, and later one inbox or chat.

## Index

| Tool | What it unlocks in the brief | Stage | Difficulty | Guide |
|---|---|---|---|---|
| Jira | Your open issues, what moved overnight, what is stuck | 2 (tasks) | Easy | [jira.md](jira.md) |
| Linear | Your assigned issues, cycle progress, what is blocked | 2 (tasks) | Easy | [linear.md](linear.md) |
| GitHub | Issues assigned to you, PRs waiting on your review, your PRs waiting on others | 2 (tasks) | Easy to medium | [github.md](github.md) |
| Notion | Rows from your tasks database, recently edited docs | 2 (tasks) | Easy | [notion.md](notion.md) |
| Google Calendar | Today's meetings, prep needed, free blocks | 3 (calendar and meetings) | Easy (Claude Code), medium (others) | [google-calendar.md](google-calendar.md) |
| Outlook Calendar | Today's meetings from Microsoft 365, prep needed, free blocks | 3 (calendar and meetings) | Medium (needs a work account and often an admin) | [outlook-calendar.md](outlook-calendar.md) |
| Granola | Decisions and action items from yesterday's meetings | 3 (calendar and meetings) | Easy | [granola.md](granola.md) |
| Confluence | Action items from meeting notes pages | 3 (calendar and meetings) | Easy (same connector as Jira) | [confluence.md](confluence.md) |
| Notes folder | Action items from your own meeting notes files | 3 (calendar and meetings) | Easiest (no connector) | [notes-folder.md](notes-folder.md) |
| Gmail | Emails that need a reply or a decision, ranked | 4 (inbox and chat) | Easy (Claude Code), medium (others) | [gmail.md](gmail.md) |
| Outlook Mail | Emails that need a reply or a decision, ranked | 4 (inbox and chat) | Medium (needs a work account and often an admin) | [outlook-mail.md](outlook-mail.md) |
| Slack | Mentions, threads waiting on you, decisions in your channels | 4 (inbox and chat) | Easy (Claude Code), hard (OpenCode) | [slack.md](slack.md) |
| Microsoft Teams | Mentions, chats waiting on you, decisions in your channels | 4 (inbox and chat) | Medium to hard (admin consent) | [teams.md](teams.md) |

Stage 1 (your profile) needs no connector.

## Client support at a glance

| Tool | Claude Code | OpenCode | Codex CLI |
|---|---|---|---|
| Jira, Confluence | Yes (official) | Yes (official) | Yes (official) |
| Linear | Yes (official) | Yes (official) | Yes (official) |
| GitHub | Yes (official) | Yes (official) | Yes (official) |
| Notion | Yes (official) | Yes (official) | Yes (official) |
| Granola | Yes (official) | Yes (official URL, generic setup) | Yes (official URL, generic setup) |
| Google Calendar, Gmail | Yes (claude.ai connector) | Community server, or Google's official server if you are in its preview | Same as OpenCode |
| Outlook Calendar, Outlook Mail, Teams | Yes (claude.ai Microsoft 365 connector, work accounts) | Community server, or Microsoft Work IQ with admin setup | Same as OpenCode |
| Slack | Yes (official plugin or claude.ai connector) | Not supported yet | Partly (documented by Slack, login can fail) |
| Notes folder | Yes | Yes | Yes |

## The three clients, in one minute

Every guide gives the exact lines for each client. This is what those lines do.

**Claude Code.** Add a server with `claude mcp add` in your terminal. Remote servers use `--transport http`. Then start Claude Code and type `/mcp` to sign in to any server that uses OAuth. `claude mcp list` shows what is connected. If you log in to Claude Code with a claude.ai account, the connectors you turned on at claude.ai/customize/connectors show up in Claude Code too, so for several tools you do not need a command at all.

**OpenCode.** Add servers to the `mcp` block of your `opencode.json`. Remote servers use `"type": "remote"` and a `url`. Local servers use `"type": "local"` and a `command` array. OpenCode starts the OAuth sign in on its own; to run it by hand use `opencode mcp auth <name>`. You can put secrets in environment variables and refer to them as `{env:VAR_NAME}`.

**Codex CLI.** Add servers to `~/.codex/config.toml` as `[mcp_servers.<name>]`, or run `codex mcp add <name> --url <url>`. Sign in to OAuth servers with `codex mcp login <name>`. `codex mcp list` shows what is connected. Some vendor guides (for example Linear's) say older Codex versions need this before OAuth works:

```toml
[features]
experimental_use_rmcp_client = true
```

Codex's own current MCP page does not mention it. If `codex mcp login` says OAuth is not supported, update Codex first, then try adding that flag.

## Two rules every guide follows

1. **Read-only wherever the tool allows it.** If the server has a read-only mode or a read-only token, the guide uses it.
2. **The loop never writes to your tools on its own.** Anything it drafts (a comment, a reply, a ticket) waits in your review queue, and nothing leaves until you say yes to that one item. Briefs, drafts and logs stay in the `morning/` folder on your machine.

## Where the settings go

Each guide ends with a `sources:` block for `morning/config.yml`. The `tool` value is always the guide's file name without `.md`, for example `tool: google-calendar`.
