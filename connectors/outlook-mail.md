# Outlook Mail (Microsoft 365)

## What it unlocks

Outlook Mail feeds the **inbox** section of your brief: emails that need a reply or a decision from you, ranked by how much they matter to your goals, with automated notifications pushed down.

Example line: "Needs a decision: finance asked which budget line the new tool goes on (yesterday). 22 notifications skipped."

## Connect it

Company Microsoft 365 accounts usually need an IT admin to approve access once. There are three routes:

1. **Claude's Microsoft 365 connector** (Claude Code only). Official and read-only by default. Needs a work or school account and one-time approval by a Microsoft Entra Global Administrator. Personal accounts (outlook.com, hotmail.com, live.com) do not work.
2. **Microsoft Work IQ** (`@microsoft/workiq`), Microsoft's own MCP server for Microsoft 365 data. Needs admin consent in your tenant and a usage-based Copilot billing plan set up by your organization.
3. **The community server `@softeria/ms-365-mcp-server`** (open source, not made by Microsoft). Works with personal accounts too and has a `--read-only` flag. Company accounts may still need admin approval.

### Claude Code

1. Go to claude.ai/customize/connectors and connect **Microsoft 365**. On Team and Enterprise plans an owner must enable it first.
2. If you see a consent error, your Microsoft admin must grant tenant consent once. Send them the setup article in Sources.
3. Start Claude Code (logged in with the same claude.ai account) and type `/mcp`. Microsoft 365 should be listed as coming from claude.ai.

Leave the optional write tools off.

### OpenCode

Community server, mail tools only, read-only. Sign in once from a terminal:

```bash
npx @softeria/ms-365-mcp-server --login
```

Follow the link and code it prints. Then in `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "outlook-mail": {
      "type": "local",
      "command": ["npx", "-y", "@softeria/ms-365-mcp-server", "--read-only", "--preset", "mail"],
      "enabled": true
    }
  }
}
```

For a work or school account, add `"--org-mode"` to the command.

Official alternative: Work IQ runs as `npx -y @microsoft/workiq mcp` after `workiq accept-eula`. It needs the admin and billing setup above, and its docs do not describe a read-only mode, so check the current docs first.

### Codex CLI

Sign in once with `npx @softeria/ms-365-mcp-server --login`, then in `~/.codex/config.toml`:

```toml
[mcp_servers.outlook-mail]
command = "npx"
args = ["-y", "@softeria/ms-365-mcp-server", "--read-only", "--preset", "mail"]
```

Add `"--org-mode"` to `args` for a work or school account. Work IQ is the official alternative, as above.

If you also connected Outlook Calendar with the same server, you can run one server with `--preset mail,calendar` instead of two.

## Prove it works

Onboarding asks the agent:

> List the 5 most recent emails in my Outlook inbox, with sender, subject and received time. Do not open attachments.

**Pass:** the 5 emails at the top of your inbox, in the same order.

## Scope it

You choose:

- **Which folders.** Inbox only, or also certain folders (or the Focused inbox).
- **What to skip.** Automated senders, notification folders, newsletters.
- **How far back.** Usually since the last brief.
- **Mine first.** Whether emails sent directly to you rank above ones where you are copied.

```yaml
sources:
  inbox:
    tool: outlook-mail
    scope: "Inbox, received since the last brief; skip noreply senders and the Notifications folder"
    mine_first: true
```

## Privacy

- **Reads:** sender, subject, time and body of emails in your scope. Not attachments.
- **Writes:** none. The claude.ai connector is read-only unless your admin enables write tools; the community server runs with `--read-only`. Drafted replies stay in your local review queue; you send them yourself.
- **Stays local:** the brief, drafts and logs live in `morning/` on your machine. Email content is sent to your agent client's model while it writes the brief, so keep the scope narrow.

## If it fails

1. **"Need admin approval".** Normal for company Microsoft 365. Ask your IT admin to consent once and share the setup link in Sources.
2. **Personal account rejected by the claude.ai connector.** Use the community server instead.
3. **Community server sees no mail on a work account.** Add `--org-mode` and sign in again with `--login`.
4. **Sign in expired.** Run `npx @softeria/ms-365-mcp-server --login` again.
5. **The brief is full of notifications.** Add the senders or folders to skip in `scope`.

## Sources (checked 2026-10)

- Claude Microsoft 365 connector setup: https://support.claude.com/en/articles/12542951-set-up-the-microsoft-365-connector
- Microsoft Work IQ CLI and MCP server: https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/work-iq/cli
- Community server: https://github.com/Softeria/ms-365-mcp-server
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
