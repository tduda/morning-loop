# GitHub (issues and pull requests)

## What it unlocks

GitHub feeds the **tasks** section of your brief: issues assigned to you, pull requests waiting on your review, and your own pull requests that are waiting on someone else.

Example line: "2 PRs wait on your review in web-app (oldest: 3 days). Your PR on the signup form has 1 unresolved comment."

## Connect it

Use GitHub's official MCP server. The simplest path is the hosted (remote) version:

```
https://api.githubcopilot.com/mcp/
```

You sign in with a **personal access token (PAT)**. Make a read-only one:

1. Go to GitHub, Settings, Developer settings, Personal access tokens, **Fine-grained tokens**, Generate new token.
2. Pick the repositories the loop should see (only those).
3. Under Repository permissions set **Issues: Read-only** and **Pull requests: Read-only**. Metadata: Read-only is added for you.
4. Copy the token and keep it out of any shared file. Below it lives in an environment variable called `GITHUB_PAT`.

Turn on the server's **read-only mode** too: send the header `X-MCP-Readonly: true` (shown below), or add `/readonly` to the end of the URL. That way write tools are hidden even if the token could do more.

### Claude Code

```bash
claude mcp add-json github '{"type":"http","url":"https://api.githubcopilot.com/mcp/","headers":{"Authorization":"Bearer YOUR_GITHUB_PAT","X-MCP-Readonly":"true"}}'
```

Replace `YOUR_GITHUB_PAT` with your token. This form needs a recent Claude Code (GitHub's guide says 2.1.1 or later).

### OpenCode

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "github": {
      "type": "remote",
      "url": "https://api.githubcopilot.com/mcp/",
      "enabled": true,
      "oauth": false,
      "headers": {
        "Authorization": "Bearer {env:GITHUB_PAT}",
        "X-MCP-Readonly": "true"
      }
    }
  }
}
```

Set `GITHUB_PAT` in your shell before you start OpenCode.

### Codex CLI

In `~/.codex/config.toml`:

```toml
[mcp_servers.github]
url = "https://api.githubcopilot.com/mcp/"
bearer_token_env_var = "GITHUB_PAT"
http_headers = { "X-MCP-Readonly" = "true" }
```

Set `GITHUB_PAT` in your shell before you start Codex.

### Running it locally instead (optional)

If you prefer not to use the hosted server, GitHub publishes a Docker image, `ghcr.io/github/github-mcp-server`. Pass your token as `GITHUB_PERSONAL_ACCESS_TOKEN`, and set `GITHUB_READ_ONLY=true` for read-only mode. You can limit tools with `GITHUB_TOOLSETS` (for example `issues,pull_requests`). Exact lines per client: check the current docs at https://github.com/github/github-mcp-server/tree/main/docs/installation-guides

## Prove it works

Onboarding asks the agent:

> List the 5 most recently updated open issues or pull requests assigned to me or requesting my review, with repo, number, title and last updated date.

**Pass:** up to 5 real items you recognise. If the list is empty but you have open work, the token probably cannot see that repository.

## Scope it

You choose:

- **Which repositories** (or an organization).
- **What counts.** Issues assigned to you, PRs requesting your review, your own open PRs, or all three.
- **Mine first.** Whether your own items lead the section.

```yaml
sources:
  tasks:
    tool: github
    scope: "repos: acme/web-app, acme/api; issues assigned to me; PRs requesting my review; my open PRs"
    mine_first: true
```

## Privacy

- **Reads:** issues, pull requests, review requests and comments in the repositories your token can see.
- **Writes:** none in read-only mode. The loop never comments, reviews or merges without your per-item yes.
- **Stays local:** the brief, drafts and logs live in `morning/` on your machine. Your token stays in your environment or client config, never in `morning/config.yml`.

## If it fails

1. **401 or "bad credentials".** The token is wrong, expired, or the environment variable is not set in the shell that started your client. Print it with `echo $GITHUB_PAT | head -c 4` to check it is there.
2. **Some repositories are missing.** A fine-grained token only sees the repos you picked. Edit the token and add them. Organization repos may also need the organization to approve fine-grained tokens.
3. **Claude Code rejects `add-json`.** Update Claude Code, or use `claude mcp add --transport http github https://api.githubcopilot.com/mcp/ --header "Authorization: Bearer YOUR_GITHUB_PAT" --header "X-MCP-Readonly: true"`.
4. **Too many tools, slow answers.** Use the local Docker version with `GITHUB_TOOLSETS=issues,pull_requests`.

## Sources (checked 2026-10)

- GitHub MCP server: https://github.com/github/github-mcp-server
- Claude Code install guide: https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-claude.md
- OpenCode install guide: https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-opencode.md
- Codex install guide: https://github.com/github/github-mcp-server/blob/main/docs/installation-guides/install-codex.md
- Claude Code MCP: https://code.claude.com/docs/en/mcp
