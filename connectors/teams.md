# Microsoft Teams

## What it unlocks

Teams feeds the **chat** section of your brief: mentions you have not answered, chats waiting on you, and decisions made in your channels while you were away.

Example line: "Product team, General channel: you were asked to review the rollout plan (unanswered since yesterday). 1 chat is waiting on your reply."

## Connect it

Teams only works with **work or school** Microsoft accounts, and companies almost always need an IT admin to approve access once. Plan for that before you start. There are three routes:

1. **Claude's Microsoft 365 connector** (Claude Code only). Official, covers Teams chats, channels and meeting transcripts, read-only by default. Needs one-time approval by a Microsoft Entra Global Administrator.
2. **Microsoft Work IQ** (`@microsoft/workiq`), Microsoft's own MCP server for Microsoft 365 data, including Teams messages. Needs admin consent and a usage-based Copilot billing plan set up by your organization.
3. **The community server `@softeria/ms-365-mcp-server`** (open source, not made by Microsoft). Its `teams` tools read teams, channels and messages; sending lives in a separate `teams-write` set you leave off. Needs `--org-mode`, and your admin may still need to approve it.

### Claude Code

1. Go to claude.ai/customize/connectors and connect **Microsoft 365**. On Team and Enterprise plans an owner must enable it first.
2. If you see a consent error, your Microsoft admin must grant tenant consent once. Send them the setup article in Sources.
3. Start Claude Code (logged in with the same claude.ai account) and type `/mcp`. Microsoft 365 should be listed as coming from claude.ai.

Leave the optional write tools off (they let Claude send Teams messages).

### OpenCode

Community server, Teams read tools only. Sign in once from a terminal:

```bash
npx @softeria/ms-365-mcp-server --org-mode --login
```

Then in `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "teams": {
      "type": "local",
      "command": ["npx", "-y", "@softeria/ms-365-mcp-server", "--org-mode", "--read-only", "--preset", "teams"],
      "enabled": true
    }
  }
}
```

Official alternative: Work IQ runs as `npx -y @microsoft/workiq mcp` after `workiq accept-eula`. It needs the admin and billing setup above, and its docs do not describe a read-only mode, so check the current docs first.

### Codex CLI

Sign in once with `npx @softeria/ms-365-mcp-server --org-mode --login`, then in `~/.codex/config.toml`:

```toml
[mcp_servers.teams]
command = "npx"
args = ["-y", "@softeria/ms-365-mcp-server", "--org-mode", "--read-only", "--preset", "teams"]
```

Work IQ is the official alternative, as above.

If you already run this server for Outlook, use one server with `--preset mail,calendar,teams` instead of three.

## Prove it works

Onboarding asks the agent:

> List the Teams channels I am a member of, then show the 5 most recent messages in the channel I named, with sender, time and first line.

**Pass:** channels you recognise and recent messages that match what you see in Teams.

## Scope it

You choose:

- **Which teams and channels.** A short list, for example the Product team's General and Releases channels.
- **Chats and mentions.** Whether 1:1 and group chats and your mentions are included.
- **How far back.** Usually since the last brief.
- **Mine first.** Whether mentions of you rank above general channel activity.

```yaml
sources:
  chat:
    tool: teams
    scope: "team Product: General, Releases; plus my mentions and chats since the last brief"
    mine_first: true
```

## Privacy

- **Reads:** messages, threads and mentions in the teams, channels and chats you scope.
- **Writes:** none. The claude.ai connector is read-only unless your admin enables write tools; the community server runs with `--read-only` and without `teams-write`. Drafted replies stay in your local review queue.
- **Stays local:** the brief, drafts and logs live in `morning/` on your machine. Message content is sent to your agent client's model while it writes the brief, so list only the channels you need.

## If it fails

1. **"Need admin approval".** Expected for Teams. Ask your IT admin to consent once and share the setup link in Sources.
2. **Personal Microsoft account.** Teams data through these routes needs a work or school account. There is no supported route for personal Teams.
3. **Community server shows no Teams tools.** You left out `--org-mode`. Add it to both the login and the config, then sign in again.
4. **A channel is missing.** You only see channels you are a member of. Check in Teams, then fix `scope`.
5. **Sign in expired.** Run the `--login` command again.

## Sources (checked 2026-10)

- Claude Microsoft 365 connector setup: https://support.claude.com/en/articles/12542951-set-up-the-microsoft-365-connector
- Microsoft Work IQ CLI and MCP server: https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/work-iq/cli
- Community server: https://github.com/Softeria/ms-365-mcp-server
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
