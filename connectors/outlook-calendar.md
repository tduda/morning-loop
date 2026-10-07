# Outlook Calendar (Microsoft 365)

## What it unlocks

Outlook Calendar feeds the **calendar** section of your brief: today's meetings, which ones need prep, and where your free blocks are.

Example line: "5 meetings today, 3 back to back after lunch. The 09:30 planning call has an agenda you have not read."

## Connect it

Microsoft calendars are harder to connect than most tools, because company Microsoft 365 accounts usually need an IT admin to approve access once. There are three routes:

1. **Claude's Microsoft 365 connector** (Claude Code only). Official, read-only by default. Needs a work or school account and one-time approval by a Microsoft Entra Global Administrator. Personal accounts (outlook.com, hotmail.com, live.com) do not work.
2. **Microsoft Work IQ** (`@microsoft/workiq`), Microsoft's own MCP server for Microsoft 365 data. Needs admin consent in your tenant and a usage-based Copilot billing plan set up by your organization. Good if your company already uses it.
3. **The community server `@softeria/ms-365-mcp-server`** (open source, not made by Microsoft). Works with personal accounts too, and has a `--read-only` flag. Company accounts may still need admin approval.

### Claude Code

Use the claude.ai Microsoft 365 connector:

1. Go to claude.ai/customize/connectors and connect **Microsoft 365**. On Team and Enterprise plans an owner must enable it first.
2. If you see a consent error, your Microsoft admin must grant tenant consent once. Send them the setup article in Sources.
3. Start Claude Code (logged in with the same claude.ai account) and type `/mcp`. Microsoft 365 should be listed as coming from claude.ai.

Leave the optional write tools off. You only need reading.

### OpenCode

Community server, calendar tools only, read-only. Sign in once from a terminal:

```bash
npx @softeria/ms-365-mcp-server --login
```

Follow the link and code it prints. Then in `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "outlook-calendar": {
      "type": "local",
      "command": ["npx", "-y", "@softeria/ms-365-mcp-server", "--read-only", "--preset", "calendar"],
      "enabled": true
    }
  }
}
```

For a work or school account, add `"--org-mode"` to the command.

Official alternative: Work IQ runs as `npx -y @microsoft/workiq mcp` after you accept its license with `workiq accept-eula`. It needs the admin and billing setup described above, and its docs do not describe a read-only mode, so check the current docs before using it.

### Codex CLI

Sign in once with `npx @softeria/ms-365-mcp-server --login`, then in `~/.codex/config.toml`:

```toml
[mcp_servers.outlook-calendar]
command = "npx"
args = ["-y", "@softeria/ms-365-mcp-server", "--read-only", "--preset", "calendar"]
```

Add `"--org-mode"` to `args` for a work or school account. Work IQ is the official alternative, as described under OpenCode.

## Prove it works

Onboarding asks the agent:

> List my Outlook calendar events for today and tomorrow, with start time, title and organizer.

**Pass:** the meetings you expect, at the right times in your time zone.

## Scope it

You choose:

- **Which calendars.** Your main calendar, plus shared or group calendars you follow.
- **What to skip.** Declined events, all-day events, "tentative" holds.
- **Mine first.** Whether meetings you organise come first.

```yaml
sources:
  calendar:
    tool: outlook-calendar
    scope: "calendars: Calendar (primary), Product Team group calendar; skip declined"
    mine_first: true
```

## Privacy

- **Reads:** event titles, times, attendees, bodies and links on the calendars you scope.
- **Writes:** none. The claude.ai connector is read-only unless your admin enables write tools; the community server runs with `--read-only`. The loop never accepts, declines or creates events.
- **Stays local:** the brief, drafts and logs live in `morning/` on your machine. Access always follows your own Microsoft 365 permissions.

## If it fails

1. **"Need admin approval".** Your company requires an admin to consent once. This is normal for Microsoft 365. Ask your IT admin and share the setup link in Sources.
2. **Personal account rejected by the claude.ai connector.** It only supports work or school accounts. Use the community server instead.
3. **Community server sees no calendars on a work account.** Add `--org-mode`. Then sign in again with `--login`.
4. **Sign in expired.** Run `npx @softeria/ms-365-mcp-server --login` again.
5. **Too many tools load.** Keep `--preset calendar` so only calendar tools appear.

## Sources (checked 2026-10)

- Claude Microsoft 365 connector setup: https://support.claude.com/en/articles/12542951-set-up-the-microsoft-365-connector
- Microsoft Work IQ CLI and MCP server: https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/work-iq/cli
- Community server: https://github.com/Softeria/ms-365-mcp-server
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- OpenCode MCP servers: https://opencode.ai/docs/mcp-servers/
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
