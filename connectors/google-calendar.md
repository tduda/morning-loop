# Google Calendar

## What it unlocks

Google Calendar feeds the **calendar** section of your brief: today's meetings, which ones need prep, and where your free blocks are.

Example line: "4 meetings today. The 14:00 roadmap review has a doc attached you have not opened. Longest free block: 10:00 to 12:00."

## Connect it

There are three routes. Pick the first one your client supports.

1. **Claude's Google Calendar connector** (Claude Code only). Official, read-only, easiest.
2. **Google's official Calendar MCP server** at `https://calendarmcp.googleapis.com/mcp/v1`. It is real, but in a Developer Preview: you must be in the Google Workspace Developer Preview Program, create a Google Cloud project, and make your own OAuth client. Most people cannot use it yet.
3. **A widely used community server, `workspace-mcp`** (open source, runs on your machine). It needs a Google Cloud OAuth client too, but no preview access. It is not made by Google.

### Claude Code

Use the claude.ai connector:

1. Go to claude.ai/customize/connectors.
2. Find **Google Calendar**, select **Connect**, and sign in to Google.
3. Start Claude Code (logged in with the same claude.ai account) and type `/mcp`. Google Calendar should be listed as coming from claude.ai.

The connector is **read-only**: it cannot create, change or delete events. It is on Pro, Max, Team and Enterprise plans; on Team and Enterprise an owner must enable it first.

Known issue: some people see only an "authenticate" tool for this connector inside Claude Code, and no calendar tools. If that happens to you, use the community server below.

### OpenCode

Use the community `workspace-mcp` server, read-only, calendar only. First create a Google OAuth client:

1. In Google Cloud Console, create a project and enable the Google Calendar API.
2. Set up the OAuth consent screen, then create an OAuth client of type **Desktop app**.
3. Put the client id and secret in your shell as `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`.

You also need `uv` installed (it provides `uvx`). Then in `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "google-calendar": {
      "type": "local",
      "command": ["uvx", "workspace-mcp", "--tools", "calendar", "--read-only"],
      "enabled": true,
      "environment": {
        "GOOGLE_OAUTH_CLIENT_ID": "{env:GOOGLE_OAUTH_CLIENT_ID}",
        "GOOGLE_OAUTH_CLIENT_SECRET": "{env:GOOGLE_OAUTH_CLIENT_SECRET}"
      }
    }
  }
}
```

The first time the agent uses it, the server gives you a Google sign in link. If you are in Google's Developer Preview, you can point a `remote` server at `https://calendarmcp.googleapis.com/mcp/v1` instead; check the current docs for the OAuth client settings it needs.

### Codex CLI

Same community server, in `~/.codex/config.toml`:

```toml
[mcp_servers.google-calendar]
command = "uvx"
args = ["workspace-mcp", "--tools", "calendar", "--read-only"]
env_vars = ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"]
```

`env_vars` passes those two values through from your shell. If you are in Google's Developer Preview, Codex can use the official URL with a pre-registered OAuth client (`codex mcp add <name> --url <url> --oauth-client-id <id>`); check the current docs for the client secret and redirect settings.

### Minimum Google scopes

Google's own guide lists read-only Calendar scopes: `calendar.calendarlist.readonly`, `calendar.events.readonly` and `calendar.events.freebusy`. When you set up the consent screen, add read-only scopes only.

## Prove it works

Onboarding asks the agent:

> List my Google Calendar events for today and tomorrow, with start time, title and number of attendees.

**Pass:** the meetings you expect, at the right times in your time zone. Wrong times usually mean a time zone setting is off (see below).

## Scope it

You choose:

- **Which calendars.** Your main calendar, plus any shared ones (a team calendar, an on-call rota).
- **What to skip.** For example all-day events, declined events, or focus blocks.
- **Mine first.** Whether meetings you organise come first.

```yaml
sources:
  calendar:
    tool: google-calendar
    scope: "calendars: primary, Team Product; skip declined and all-day events"
    mine_first: true
```

## Privacy

- **Reads:** event titles, times, attendees, descriptions and attached links on the calendars you scope.
- **Writes:** none. The claude.ai connector is read-only, and the community server runs with `--read-only`. The loop never accepts, declines or creates events.
- **Stays local:** the brief, drafts and logs live in `morning/` on your machine. With the community server, your Google tokens also stay on your machine.

## If it fails

1. **Claude Code shows only an "authenticate" tool.** Disconnect and reconnect at claude.ai/customize/connectors, restart Claude Code. If it persists, use the community server route.
2. **"Access blocked" from Google.** Your OAuth consent screen is in testing mode and your account is not a test user, or your company blocks unverified apps. Add yourself as a test user, or ask your Google Workspace admin.
3. **`uvx: command not found`.** Install `uv` (see https://docs.astral.sh/uv/) and restart your terminal.
4. **Times are off by hours.** Tell the agent your time zone in `morning/profile.md`, and check the time zone setting in Google Calendar.
5. **Team calendar missing.** Make sure you are subscribed to it in Google Calendar, then name it in `scope`.

## Sources (checked 2026-10)

- Claude Google Calendar connector: https://claude.com/docs/connectors/google/calendar
- Google Calendar MCP server (preview): https://developers.google.com/workspace/calendar/api/guides/configure-mcp-server
- Google Workspace MCP servers: https://developers.google.com/workspace/guides/configure-mcp-servers
- Community server `workspace-mcp`: https://github.com/taylorwilsdon/google_workspace_mcp
- Claude Code MCP (claude.ai connectors in Claude Code): https://code.claude.com/docs/en/mcp
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
