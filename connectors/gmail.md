# Gmail

## What it unlocks

Gmail feeds the **inbox** section of your brief: emails that need a reply or a decision from you, ranked by how much they matter to your goals, with newsletters and notifications pushed down.

Example line: "Needs a reply today: the vendor asked you to confirm the renewal date (2 days old). 14 notifications skipped."

## Connect it

There are three routes. Pick the first one your client supports.

1. **Claude's Gmail connector** (Claude Code only). Official and **read-only**: it searches and reads email, and cannot create, send or change messages.
2. **Google's official Gmail MCP server** at `https://gmailmcp.googleapis.com/mcp/v1`. It is in a Developer Preview: you must be in the Google Workspace Developer Preview Program, create a Google Cloud project, and make your own OAuth client. Most people cannot use it yet.
3. **The widely used community server `workspace-mcp`** (open source, runs on your machine, not made by Google). Needs your own Google Cloud OAuth client, but no preview access. Has a `--read-only` flag.

### Claude Code

1. Go to claude.ai/customize/connectors.
2. Find **Gmail**, select **Connect**, and sign in to Google.
3. Start Claude Code (logged in with the same claude.ai account) and type `/mcp`. Gmail should be listed as coming from claude.ai.

The connector is on Pro, Max, Team and Enterprise plans. On Team and Enterprise an owner must enable it first.

Known issue: some people see only an "authenticate" tool for this connector inside Claude Code, and no mail tools. If that happens, use the community server below.

### OpenCode

Use the community `workspace-mcp` server, read-only, Gmail only. First create a Google OAuth client:

1. In Google Cloud Console, create a project and enable the Gmail API.
2. Set up the OAuth consent screen, then create an OAuth client of type **Desktop app**.
3. Put the client id and secret in your shell as `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET`.

You also need `uv` installed (it provides `uvx`). Then in `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "gmail": {
      "type": "local",
      "command": ["uvx", "workspace-mcp", "--tools", "gmail", "--read-only"],
      "enabled": true,
      "environment": {
        "GOOGLE_OAUTH_CLIENT_ID": "{env:GOOGLE_OAUTH_CLIENT_ID}",
        "GOOGLE_OAUTH_CLIENT_SECRET": "{env:GOOGLE_OAUTH_CLIENT_SECRET}"
      }
    }
  }
}
```

The first time the agent uses it, the server gives you a Google sign in link. If you are in Google's Developer Preview you can use the official URL as a `remote` server instead; check the current docs for its OAuth client settings.

### Codex CLI

Same community server, in `~/.codex/config.toml`:

```toml
[mcp_servers.gmail]
command = "uvx"
args = ["workspace-mcp", "--tools", "gmail", "--read-only"]
env_vars = ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"]
```

For Google's preview server, Codex supports a pre-registered OAuth client (`codex mcp add <name> --url <url> --oauth-client-id <id>`); check the current docs for the rest.

### Minimum Google scope

For reading, the scope is `gmail.readonly`. Google's preview guide also lists `gmail.compose` (for drafts); leave it out, the loop does not need it.

## Prove it works

Onboarding asks the agent:

> List the 5 most recent emails in my Gmail inbox, with sender, subject and date. Do not open attachments.

**Pass:** the 5 emails you see at the top of your inbox, in the same order.

## Scope it

You choose:

- **Which mail.** Inbox only, or certain labels.
- **What to skip.** Newsletters, automated notifications, specific senders.
- **How far back.** Usually since the last brief.
- **Mine first.** Whether emails addressed directly to you rank above ones where you are copied.

```yaml
sources:
  inbox:
    tool: gmail
    scope: "in:inbox newer_than:2d -category:promotions -category:social"
    mine_first: true
```

The `scope` can use Gmail's normal search syntax.

## Privacy

- **Reads:** sender, subject, date and body of emails in your scope. It does not need attachments.
- **Writes:** none. The claude.ai connector is read-only, and the community server runs with `--read-only`. If the loop drafts a reply, the draft sits in your local review queue; you copy and send it yourself.
- **Stays local:** the brief, drafts and logs live in `morning/` on your machine. Email content is sent to your agent client's model while it writes the brief, so keep the scope as narrow as you can.

## If it fails

1. **Claude Code shows only an "authenticate" tool.** Disconnect and reconnect Gmail at claude.ai/customize/connectors and restart Claude Code. If it persists, use the community server.
2. **"Access blocked" from Google.** Your consent screen is in testing mode and you are not a test user, or your Google Workspace admin blocks unverified apps. Add yourself as a test user or ask your admin.
3. **`uvx: command not found`.** Install `uv` (https://docs.astral.sh/uv/) and restart your terminal.
4. **The brief is full of newsletters.** Add exclusions to `scope`, for example `-category:updates` or `-from:noreply`.

## Sources (checked 2026-10)

- Claude Gmail connector: https://claude.com/docs/connectors/google/gmail
- Google Workspace MCP servers (preview): https://developers.google.com/workspace/guides/configure-mcp-servers
- Gmail MCP reference: https://developers.google.com/workspace/gmail/api/reference/mcp
- Community server `workspace-mcp`: https://github.com/taylorwilsdon/google_workspace_mcp
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
