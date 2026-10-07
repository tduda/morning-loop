# Getting started (Mac and Windows)

Never used a terminal or an AI coding tool? This page is for you. It takes about 20 minutes, most of it installing things once.

## What you need

- A Mac (macOS 13 or newer) or a Windows PC (Windows 10 or 11).
- **One AI client**, logged in:
  - **Claude Code**, if you have a Claude subscription.
  - **Codex CLI**, if you have a ChatGPT plan. It's OpenAI's agent that runs on your computer; the ChatGPT app itself can't run things on your machine.
  - **OpenCode**, if you prefer to bring your own model provider.
- **Python 3.9 or newer**: Morning Loop's small helper scripts run on it.
- **Somewhere to work.** We recommend **VS Code** (free): one window shows your files, a chat with your AI client, and a terminal. Not required: a desktop app or a plain terminal works too.

## 1. Install Python

**Mac:** download it from https://www.python.org/downloads/ and run the installer. (If you'd rather, opening Terminal and typing `xcode-select --install` also gives you Python 3.)

**Windows:** download it from https://www.python.org/downloads/ and run the installer. **Tick "Add python.exe to PATH"** on the first screen. Then you can use `py` in a terminal. If the installer doesn't appear (no Python runtime behind it), or if after installing `python` still opens the Microsoft Store, go to **Settings > Apps > Advanced app settings > App execution aliases** and turn OFF the `python.exe` and `python3.exe` entries.

## 2. Install your AI client, and log in once

Follow the official page for your client; each has a one-line installer for Mac and for Windows:

- Claude Code: https://code.claude.com/docs/en/setup (it also has a desktop app if you'd rather not use a terminal)
- Codex CLI: https://learn.chatgpt.com/docs/codex/cli (also has a desktop app)
- OpenCode: https://opencode.ai/docs

Run it once and log in, so it's ready.

## 3. Install VS Code (recommended)

Download it from https://code.visualstudio.com/download. Then open the **Extensions** panel (the four squares on the left) and install your client's extension: search **Claude Code** or **Codex**. OpenCode runs in VS Code's built-in terminal (**Terminal > New Terminal**, then type `opencode`).

Using something else? Cursor, JetBrains IDEs, the client's own desktop app or a plain terminal all work. You just need to be able to open a folder and talk to your client there.

## 4. Get Morning Loop

On the GitHub page (https://github.com/tduda/morning-loop), click the green **Code** button:

- **Download ZIP**, then unzip it somewhere you'll keep it (for example your Documents folder). Choose a folder outside Downloads: if Downloads fills up and gets cleaned, the setup stops working. Simplest.
- Or, if you use Git or GitHub Desktop, **clone** it: `git clone https://github.com/tduda/morning-loop.git`. Updating later is then one click (`git pull`), and installs can tell your own changes apart from ours more precisely.

## 5. Double-click "Start here"

In the Morning Loop folder:

- **Mac:** double-click **Start here - Mac.command**. If macOS says it can't verify the developer:
  - **Before Sequoia (macOS 14 or earlier):** right-click it and choose **Open**.
  - **Sequoia or later (macOS 15+):** right-click still shows the same block. Instead, go to **System Settings > Privacy & Security**, scroll down to **"Start here - Mac.command"**, and click **Open Anyway**. (This is a one-time step.)
- **Windows:** double-click **Start here - Windows.bat**. If SmartScreen warns you, choose **More info**, then **Run anyway**.

It finds your AI client, installs Morning Loop's commands into it, and asks **where your brief should live**: press Enter for a new folder, or paste the path of a folder you already work in (it only adds one subfolder, `morning/`). Then it checks everything and tells you what to open.

Prefer typing? From the Morning Loop folder: `python3 scripts/quickstart.py` on a Mac, `py scripts\quickstart.py` on Windows.

## 6. Start onboarding

1. In VS Code: **File > Open Folder...**, and pick the folder from step 5 (the one containing `morning/`). Open your client's panel (or terminal).
2. Type **`/onboard`** and press Enter.

You'll see the stages, what each one costs in minutes and what it adds to your brief. Stage 1 takes 10 minutes and needs no tools; from the next morning you get a brief built on your goals. Then do stage 5 (5 minutes, required): it's what makes the brief appear on its own every morning. The tool stages you can do when you have time, or skip. A skipped stage is only mentioned again if it would help with something you're actually working on.

## Good to know

- **The brief is made on your computer, so it arrives when your computer is on**: at 07:52 on weekdays, or the first time you open it that morning (stage 5 sets that up).
- **On Windows** the brief is saved as a page you open; there are no notifications yet.
- **Updating:** download the ZIP again (or `git pull`), then run "Start here" again. It never overwrites a command or skill you changed; it puts the new version beside yours as `.new`. On Windows and Linux (where the setup uses copies instead of links), you must also run `py scripts\setup.py <your folder> --refresh` (or `python3` instead of `py` on Mac/Linux) so that updates reach your workspace. Do this after every download or `git pull`.
- **Removing it:** delete the `morning/` folder from your workspace, and the Morning Loop files from your client's folder (`~/.claude/commands` and `~/.claude/skills` for Claude Code, `~/.codex/prompts` and `~/.codex/skills` for Codex, `~/.config/opencode/skills` for OpenCode).
