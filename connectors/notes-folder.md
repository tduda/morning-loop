# Notes folder (no connector needed)

## What it unlocks

A folder of your own meeting notes feeds the **meetings** section of your brief: decisions and action items from notes you typed, pasted or exported.

Example line: "From your notes on the vendor call (yesterday): you owe a reply on the contract terms by Friday."

This is the easiest meetings source. If you are unsure where to start, start here.

## Connect it

There is nothing to install. Your agent can already read files on your machine. You only tell the loop where the folder is.

The folder can be:

- `morning/notes/` inside your workspace (the default, created for you), or
- any folder you already use, for example a notes app's export folder or a synced drive folder.

Plain text and Markdown (`.md`, `.txt`) work best. One file per meeting, with the date in the file name (for example `2026-10-05 design sync.md`), makes it easy for the loop to find yesterday's meetings.

### Claude Code

Nothing to add. If the folder is outside your workspace folder, Claude Code may ask for permission the first time it reads it. You can allow it once or add the folder as an extra working directory (check the current docs: https://code.claude.com/docs/en/settings).

### OpenCode

Nothing to add. If the folder is outside the folder you start OpenCode in, OpenCode may ask before reading it. Keeping notes inside your workspace avoids the question.

### Codex CLI

Nothing to add. Codex can read files in the folder you start it in. A folder elsewhere may need an approval or a sandbox setting; check the current docs: https://learn.chatgpt.com/docs/extend/mcp?surface=cli (see the configuration pages linked from there).

## Prove it works

Onboarding asks the agent:

> List the 5 most recent files in my notes folder with their dates, and give the action items from the newest one.

**Pass:** the files you expect, newest first, and action items that match what you wrote.

## Scope it

You choose:

- **Which folder** (a path).
- **Which files.** All of them, or a name pattern.
- **Mine first.** Whether action items owned by you come first.

```yaml
sources:
  meetings:
    tool: notes-folder
    scope: "path: morning/notes/; files named YYYY-MM-DD *.md; since the last brief"
    mine_first: true
```

## Privacy

- **Reads:** only files in the folder you name.
- **Writes:** the loop may add its own notes under `morning/notes/`. It never edits or deletes your notes files in another folder.
- **Stays local:** everything stays on your machine, apart from what your agent client sends its model while writing the brief.

## If it fails

1. **"No such file or directory".** The path is wrong. Use a full path, or a path relative to your workspace folder.
2. **The agent keeps asking permission.** Move the notes into `morning/notes/`, or allow the folder in your client's settings.
3. **Yesterday's meeting is missed.** Put the date in the file name, or make sure the file's modified date is right.
4. **Notes are in Word or PDF.** Export them as text or Markdown, or ask the agent whether it can read that format in your client.

## Sources (checked 2026-10)

- Workspace layout: `docs/LAYOUT.md` in this repo
- Claude Code settings: https://code.claude.com/docs/en/settings
- Codex docs: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
