# Slack

## What it unlocks

Slack feeds the **chat** section of your brief: mentions you have not answered, threads waiting on you, and decisions made in your channels while you were away.

Example line: "#team-product: you were asked to sign off the release notes (unanswered, 18 hours). A decision in #design-review moved the launch to next week."

## Connect it

Slack has an official hosted server:

```
https://mcp.slack.com/mcp
```

It uses OAuth. Two things to know first:

- **Your workspace admin must approve it.** Slack lets admins approve and manage MCP integrations. If yours has not, the sign in will fail.
- **Slack only accepts approved apps.** Slack does not let a client register itself on the fly. Claude Code works out of the box because Slack ships a ready-made Claude Code plugin. Other clients need an approved Slack app, which is why support differs below.

Slack's server has no read-only mode. It includes write tools (send messages, add reactions). The loop never uses them without your per-item yes.

### Claude Code (supported)

Install Slack's official plugin, which sets up the server for you:

```bash
claude plugin install slack
```

(or type `/plugin install slack` inside Claude Code). You are asked to sign in to your Slack workspace the first time it is used.

Or connect Slack at claude.ai/customize/connectors. It then appears in Claude Code automatically.

### OpenCode (not supported yet)

Slack's docs do not cover OpenCode, and OpenCode's sign in does not currently fit Slack's OAuth rules (Slack rejects on the fly client registration and expects a fixed callback). Community workarounds exist, but none is official. For now, use Claude Code for Slack, or leave Slack off and rely on your inbox source. Check the current docs: https://docs.slack.dev/ai/slack-mcp-server/connect-to-harnesses/

### Codex CLI (partly supported)

Slack documents this setup. In your terminal:

```bash
codex mcp add --transport http slack https://mcp.slack.com/mcp
```

Or in `~/.codex/config.toml`:

```toml
[mcp_servers.slack]
url = "https://mcp.slack.com/mcp"
auth = "oauth"
```

Then run `codex mcp list` and check `slack` shows as connected. If the sign in fails with a client id error, it is a known gap: Slack expects a pre-registered client, and your workspace may need its own approved Slack app. Check the current docs before going further.

## Prove it works

Onboarding asks the agent:

> Search Slack for the 5 most recent messages that mention me, and list channel, sender, time and the first line of each.

**Pass:** recent mentions you recognise. If you have none, ask for the 5 latest messages in one channel you named instead.

## Scope it

You choose:

- **Which channels.** A short list matters more than a long one, for example `#team-product` and `#design-review`.
- **Mentions and DMs.** Whether direct messages and mentions are included.
- **How far back.** Usually since the last brief.
- **Mine first.** Whether mentions of you rank above general channel activity.

```yaml
sources:
  chat:
    tool: slack
    scope: "channels: #team-product, #design-review; plus my mentions and DMs since the last brief"
    mine_first: true
```

## Privacy

- **Reads:** messages, threads and mentions in the channels and DMs you scope.
- **Writes:** never on its own. Drafted replies wait in your local review queue; nothing is posted until you say yes to that one item.
- **Stays local:** the brief, drafts and logs live in `morning/` on your machine. Message content is sent to your agent client's model while it writes the brief, so list only the channels you need.

## If it fails

1. **"App not approved" or sign in blocked.** Your workspace admin has to approve the Slack MCP integration. Ask them.
2. **Claude Code plugin installed, but no Slack tools.** Restart Claude Code, then type `/mcp` and sign in to `slack`.
3. **A channel is missing.** Private channels only show if you are a member. Join it, or remove it from `scope`.
4. **Codex sign in fails with a client id error.** See the Codex section: this needs an approved Slack app. Use Claude Code for Slack in the meantime.

## Sources (checked 2026-10)

- Slack MCP server overview: https://docs.slack.dev/ai/slack-mcp-server/
- Connect to Claude: https://docs.slack.dev/ai/slack-mcp-server/connect-to-claude/
- Connect to agent harnesses (Codex): https://docs.slack.dev/ai/slack-mcp-server/connect-to-harnesses/
- OpenCode OAuth callback issue: https://github.com/anomalyco/opencode/issues/18955
- Claude Code MCP: https://code.claude.com/docs/en/mcp
- Codex MCP: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
