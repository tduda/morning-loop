#!/usr/bin/env python3
"""
Get the morning brief in front of you with NO account setup.

A delivery step that requires an account is a step most people never complete,
and an undelivered brief is worth the same as no loop at all. So both channels
here cost nothing to set up.

Channels, cheapest first:

  macos       Native notification + the brief opens as a local web page.
              Zero setup. Nothing to sign up for. Works offline.
  mattermost  One incoming-webhook URL pasted into a config. No account, no
              2FA, no MCP. Your team may already live there. This is the one to
              share.
  file        Render the HTML and do nothing else (for scheduled runs where you
              only want the artifact).

Usage:
  notify.py --brief <plan.md> [--channel macos|mattermost|file] [--date Y-M-D]
            [--webhook URL] [--no-open] [--dry-run] [--root PATH]

Exit: 0 done · 2 config error · 3 delivery failed · 130 interrupted

A receipt is ALWAYS written, so HEALTH can tell "failed" from "never attempted".
That is a promise, not an aspiration: the receipt is built before anything that
can fail, every failure path writes it, and an unexpected exception or a Ctrl-C
writes it on the way out. Receipt statuses:

  sent               delivered, `sent_at` set
  rendered_not_sent  the page exists, nothing was delivered (channel `file`)
  dry_run            the page was rendered, the send was only described
  failed             carries the verbatim `error`

A `sent` receipt is never overwritten by a worse one, because run-prep greps
the receipt to decide whether to re-deliver and a downgraded receipt would make
it send today's brief twice.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = pathlib.Path(__file__).resolve().parent

PACKAGE_ROOT = HERE.parent

# THREE layouts ship this script and the depth of scripts/ under the artefact
# root differs in each, so the root has to be probed rather than counted:
#
#   standalone clone          <clone>/scripts/notify.py                depth 1
#   package copied into a     <ws>/morning/state/
#     workspace subtree         scripts/notify.py                      depth 3
#   package cloned as a       <ws>/morning-loop/scripts/notify.py      depth 2
#     workspace subdirectory
#
# Probe for the ARTEFACT ROOT: the directory that owns the trees the config's
# paths are written against and that the Phase 2c health check reads receipts
# from. Do NOT pattern-match on a config file, which is what the earlier probe
# did. The package ships a config template at its own root, so
# a glob for the config file name is true in EVERY clone, the package branch
# always won and the workspace branch was unreachable dead code. In the third
# layout that put receipts at <clone>/briefs/ inside the git clone while the
# workspace directory the config points at stayed empty.
#
# Guessing wrong is silent, so `--root` always wins and the resolved root is
# printed on success. A wrong root should be visible, not discovered in March.
WORKSPACE_MARKERS = ("morning/state",)


def find_workspace_root(start: pathlib.Path) -> pathlib.Path | None:
    """Nearest ancestor that owns a workspace artefact tree, or None.

    Walks up the way doctor.py does for its own root, but keys on the artefact
    directories instead of `.git`, because in the third layout the git root IS
    the package clone and the artefacts belong one level above it.
    """
    for p in [start, *start.parents]:
        if any((p / m).is_dir() for m in WORKSPACE_MARKERS):
            return p
    return None


def artefact_paths(root: pathlib.Path) -> tuple[str, pathlib.Path, pathlib.Path]:
    """(layout name, artefacts dir, render dir) for an already-resolved root."""
    if any((root / m).is_dir() for m in WORKSPACE_MARKERS):
        artifacts = root / "morning" / "state"
        return "workspace", artifacts, root / "morning" / "briefs" / "rendered"
    artifacts = root / "briefs"
    return "package", artifacts, artifacts / "rendered"


REPO = PACKAGE_ROOT
LAYOUT = "package"
ARTIFACTS = REPO / "briefs"
RENDER_DIR = ARTIFACTS / "rendered"
INDEX = ARTIFACTS / "brief-index.json"
RECEIPTS = ARTIFACTS / "receipts"


def configure_roots(explicit: str | None = None) -> None:
    global REPO, LAYOUT, ARTIFACTS, RENDER_DIR, INDEX, RECEIPTS
    if explicit:
        REPO = pathlib.Path(explicit).expanduser().resolve()
        if not REPO.is_dir():
            # Not fatal: the writes below mkdir their parents, and dying here
            # would be the one failure path with nowhere to leave a receipt.
            print(f"notify: --root does not exist yet, will create under {REPO}",
                  file=sys.stderr)
    else:
        # cwd first: the scripts are linked into the workspace, so HERE resolves to
        # the package clone (fresh-install test, 2026-10-05).
        REPO = find_workspace_root(pathlib.Path.cwd()) or find_workspace_root(HERE) or PACKAGE_ROOT
    LAYOUT, ARTIFACTS, RENDER_DIR = artefact_paths(REPO)
    INDEX = ARTIFACTS / "brief-index.json"
    RECEIPTS = ARTIFACTS / "receipts"


configure_roots()

# The in-progress receipt. Built before anything that can fail, so that every
# exit path -- die(), an unexpected exception, a Ctrl-C -- has one to write.
RECEIPT: dict | None = None


def record_failure(msg: str, **extra: object) -> None:
    """Leave a `failed` receipt carrying whatever we know so far."""
    if RECEIPT is None:
        return
    try:
        write_receipt(RECEIPT | {"status": "failed", "error": msg} | dict(extra))
    except OSError as e:
        print(f"notify: could not even write the failure receipt: {e}", file=sys.stderr)


def die(code: int, msg: str, **extra: object) -> None:
    """Fail loudly AND leave a receipt. A failure with no artifact is
    indistinguishable from never having run, which is the whole bug class this
    loop exists to avoid."""
    print(f"notify: {msg}", file=sys.stderr)
    record_failure(msg, **extra)
    raise SystemExit(code)


# --------------------------------------------------------------------------- brief id
def load_index() -> dict:
    if INDEX.exists():
        try:
            return json.loads(INDEX.read_text())
        except json.JSONDecodeError:
            print("notify: brief-index.json is corrupt, starting a new one", file=sys.stderr)
    return {"next_id": 1, "briefs": {}}


def assign_id(idx: dict, date: str, brief_path: str, subject: str) -> int:
    """Same date always maps to the same id, so a re-delivery never burns a number."""
    for bid, rec in idx["briefs"].items():
        if rec.get("date") == date:
            return int(bid)
    bid = idx["next_id"]
    idx["briefs"][str(bid)] = {
        "id": bid, "date": date, "plan_file": brief_path, "subject": subject,
    }
    idx["next_id"] = bid + 1
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(idx, indent=2) + "\n")
    return bid


def write_receipt(rec: dict) -> None:
    """Write today's receipt, but NEVER downgrade a good one.

    Once the brief has reached the person, that evidence outlives whatever
    happens next: a second channel that fails, a watchdog kill, a Ctrl-C. It is
    also load-bearing rather than tidy, because run-prep greps this file for
    `"status": "sent"` to decide whether to re-deliver, so a downgraded receipt
    would send today's brief a second time.
    """
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    out = RECEIPTS / f"{rec['date']}.json"
    prior = None
    if out.exists():
        try:
            prior = json.loads(out.read_text())
        except (json.JSONDecodeError, OSError):
            prior = None
    if rec.get("status") != "sent" and isinstance(prior, dict) and prior.get("status") == "sent":
        print(f"notify: today's brief is already recorded as delivered, keeping that "
              f"receipt instead of writing '{rec.get('status')}'", file=sys.stderr)
        return
    out.write_text(json.dumps(carry_first_delivery(rec, prior), indent=2) + "\n")


def carry_first_delivery(rec: dict, prior: dict | None) -> dict:
    """Keep the FIRST delivery time across re-deliveries.

    A same-day re-delivery (the brief updated in place when drafts land, or the
    runner's safety net) rewrites `sent_at`, so on its own the receipt reports
    the LAST send. On-time tracking needs the first one: lag against the fire is
    measured to when the brief first reached the person. `on_time` is carried
    too, so a re-delivery does not erase the runner's classification.
    """
    if not isinstance(prior, dict) or prior.get("status") != "sent":
        return rec
    if rec.get("status") != "sent":
        return rec
    first = prior.get("first_sent_at") or prior.get("sent_at")
    out = dict(rec)
    if first:
        out["first_sent_at"] = first
    if "on_time" in prior and "on_time" not in out:
        out["on_time"] = prior["on_time"]
    return out


# --------------------------------------------------------------------------- md -> html
CODE_SPAN = re.compile(r"`([^`]+)`")
INLINE = [
    (re.compile(r"\[([^\]]+)\]\((https?://[^)\s\"'<>]+)\)"), r'<a href="\2">\1</a>'),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])"), r"<em>\1</em>"),
    # underscore emphasis, but never inside a word so snake_case survives
    (re.compile(r"(?<![\w_])_([^_\n]+)_(?![\w_])"), r"<em>\1</em>"),
]


def inline(text: str) -> str:
    """Code spans are extracted BEFORE the emphasis rules run, otherwise markup
    inside them gets mangled (mcp__*Atlassian* turning into an <em>)."""
    out = html.escape(text, quote=False)

    stash: list[str] = []

    def park(m: re.Match) -> str:
        stash.append(m.group(1))
        return f"\x00{len(stash) - 1}\x00"

    out = CODE_SPAN.sub(park, out)
    for pat, rep in INLINE:
        out = pat.sub(rep, out)
    for i, code in enumerate(stash):
        out = out.replace(f"\x00{i}\x00", f"<code>{code}</code>")
    return out


TABLE_ROW = re.compile(r"^\|.*\|$")
TABLE_SEP = re.compile(r"^\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?$")


def _table_cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def md_to_html(md: str) -> str:
    """Deliberately small. Handles what the brief actually uses and nothing else."""
    lines, body, list_stack = md.splitlines(), [], []
    n = len(lines)

    def close_lists(to: int = 0) -> None:
        while len(list_stack) > to:
            body.append(f"</{list_stack.pop()}>")

    para: list[str] = []

    def flush_para() -> None:
        if para:
            body.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    i = 0
    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_para(); close_lists(); i += 1; continue
        if re.fullmatch(r"-{3,}|_{3,}|\*{3,}", stripped):
            flush_para(); close_lists(); body.append("<hr>"); i += 1; continue

        m = re.match(r"```(\w*)\s*$", stripped)
        if m:
            # Fenced code block — everything until a closing ``` is verbatim, never
            # re-parsed as markdown. Missing before 2026-08-31: a render:section
            # skill's output arrived wrapped in a fence (to signal "preserve this
            # exactly"), and without this the literal ``` lines fell through to
            # plain paragraph text — including once landing outside any <li>,
            # nested directly in a <ul>, invalid HTML that looked like a rendering
            # error to the reader. An unterminated fence (no closing ```) still
            # renders everything to end-of-document as code rather than losing it.
            flush_para(); close_lists()
            lang = m.group(1)
            code_lines = []
            i += 1
            while i < n and lines[i].strip() != "```":
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip the closing fence (harmless if we ran off the end)
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            body.append(f"<pre><code{cls}>{html.escape(chr(10).join(code_lines))}</code></pre>")
            continue

        if TABLE_ROW.match(stripped) and i + 1 < n and TABLE_SEP.match(lines[i + 1].strip()):
            flush_para(); close_lists()
            header = _table_cells(stripped)
            body.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in header) + "</tr></thead><tbody>")
            i += 2
            while i < n and TABLE_ROW.match(lines[i].strip()):
                row = _table_cells(lines[i].strip())
                body.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>")
                i += 1
            body.append("</tbody></table>")
            continue

        m = re.match(r"(#{1,6})\s+(.*)", stripped)
        if m:
            flush_para(); close_lists()
            lvl = min(len(m.group(1)) + 1, 6)   # h1 in the doc becomes h2 on the page
            body.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1; continue

        m = re.match(r"[-*+]\s+\[[ xX]\]\s+(.*)|[-*+]\s+(.*)", stripped)
        if m:
            flush_para()
            if not list_stack:
                list_stack.append("ul"); body.append("<ul>")
            body.append(f"<li>{inline(m.group(1) or m.group(2))}</li>")
            i += 1; continue

        m = re.match(r"\d+[.)]\s+(.*)", stripped)
        if m:
            flush_para()
            if not list_stack:
                list_stack.append("ol"); body.append("<ol>")
            body.append(f"<li>{inline(m.group(1))}</li>")
            i += 1; continue

        para.append(stripped)
        i += 1

    flush_para(); close_lists()
    return "\n".join(body)


# --------------------------------------------------------------- brief summarising
# Match BOTH the typed headings (SOLVE / ASK / HUMAN) and the older emoji ones
# (🤖 draft / 🟡 decision / 🧠 your turn), because a plan file written by either
# format must summarise correctly. Getting this wrong is not cosmetic: the first
# typed brief reported "0 decisions" while carrying 3 ASKs, which is exactly the
# number a person would act on.
SECTIONS = [
    ("drafts", re.compile(r"^##\s*🤖")),
    ("asks", re.compile(r"^##\s*(❓|🟡)")),
    ("your_turn", re.compile(r"^##\s*🧠")),
]
# Headings that end a counted section without starting a new one.
STOP = re.compile(r"^##\s*(🗑️|✅|Findings|Honesty|Run economics)")


# The brief decorates its headings ("## ── TOP OF YOUR LIST ──"), and the undecorated
# pattern never matched, so every notification led with the first ASK instead of the
# brief's own top item.
TOP_HEADING = re.compile(r"^##+\s*[─—\-\s]*TOP OF YOUR LIST", re.I)


def _explicit_top(md: str):
    """The brief states its own top item under '## TOP OF YOUR LIST'. Use it.

    Before 2026-08-20 this function did not exist and `top` was whatever the FIRST
    bullet in the asks/decisions section happened to be. That mis-picked the top
    item on four consecutive runs, because the first ASK is rarely the most
    important thing in the brief. The brief already says what leads; read that.
    """
    lines = md.splitlines()
    for i, raw in enumerate(lines):
        if TOP_HEADING.match(raw.strip()):
            for follow in lines[i + 1:]:
                t = follow.strip()
                if not t:
                    continue
                if t.startswith("#") or t.startswith("---"):
                    break          # section ended without content
                return strip_md(t)
            break
    return None


def summarise(md: str) -> dict:
    """Counts per bucket + the single most important line, for the notification."""
    counts = {k: 0 for k, _ in SECTIONS}
    current = None
    top = _explicit_top(md)

    for raw in md.splitlines():
        line = raw.strip()
        matched = False
        for key, pat in SECTIONS:
            if pat.match(line):
                current, matched = key, True
                break
        if matched:
            continue
        if line.startswith("##"):
            current = None
            continue
        # Count only TOP-LEVEL bullets. Indented sub-bullets are elaboration on the
        # item above them, not separate items, and counting them inflated every
        # number in the notification (9/21/13 where the truth was 2/8/12).
        indent = len(raw) - len(raw.lstrip())
        # Drafts are the checkbox lines only: the SOLVE section also lists
        # "Skipped, with reasons" bullets, which once counted 2 drafts as 5.
        # Asks and your-turn items are bullets OR numbered items: the brief numbers
        # them, and a bullets-only match read a brief with one ASK as zero.
        if current == "drafts":
            item = indent <= 1 and re.match(r"^[-*]\s+\[[ xX]\]\s*\S", line)
        else:
            item = current and indent <= 1 and re.match(r"^([-*]|\d+\.)\s+(\[[ xX]\]\s*)?\S", line)
        if item:
            counts[current] += 1
            if current in ("asks", "decisions") and top is None:
                top = strip_md(line)

    if top is None:                      # fall back to the first bold statement
        m = re.search(r"^\s*[-*]?\s*\*\*(.+?)\*\*", md, re.M)
        top = strip_md(m.group(1)) if m else "See the brief."
    return {"counts": counts, "top": top}


def strip_md(text: str) -> str:
    text = re.sub(r"^[-*]\s+(\[[ xX]\]\s*)?", "", text.strip())
    text = re.sub(r"\*\*|\*|`", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# --------------------------------------------------------------- channels
def render_html(md: str, date: str, bid: int | None) -> pathlib.Path:
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    out = RENDER_DIR / f"brief-{date}.html"
    # The reference is the whole point of the page's header: it is the handle you
    # paste into a terminal to carry this brief into a conversation. So it is the
    # first thing on the page, big, monospace, and one click to copy.
    ref = (f'''<div class="ref">
  <div class="ref-label">paste into your terminal to pick this up with Claude</div>
  <div class="ref-row">
    <code id="ref" class="ref-code">morning loop #{bid}</code>
    <button id="copy" onclick="copyRef()">Copy</button>
  </div>
</div>
<script>
function copyRef() {{
  var t = document.getElementById('ref').textContent;
  var done = function () {{
    var b = document.getElementById('copy');
    b.textContent = 'Copied'; b.classList.add('ok');
    setTimeout(function () {{ b.textContent = 'Copy'; b.classList.remove('ok'); }}, 1600);
  }};
  // navigator.clipboard needs a secure context and this page is opened over
  // file://, so the execCommand path is the one that usually runs. Keep both.
  if (navigator.clipboard && window.isSecureContext) {{
    navigator.clipboard.writeText(t).then(done, fallback);
  }} else {{ fallback(); }}
  function fallback() {{
    var a = document.createElement('textarea');
    a.value = t; a.style.position = 'fixed'; a.style.opacity = '0';
    document.body.appendChild(a); a.select();
    try {{ document.execCommand('copy'); done(); }}
    catch (e) {{ window.getSelection().selectAllChildren(document.getElementById('ref')); }}
    document.body.removeChild(a);
  }}
}}
</script>''' if bid else "")
    out.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Morning Brief #{bid or ''} {date}</title>"
        "<style>body{font-family:-apple-system,Segoe UI,sans-serif;line-height:1.55;"
        "max-width:50em;margin:2rem auto 3rem;padding:0 1.2rem;color:#1a1a1a}"
        "code{background:#f4f4f5;padding:.1em .3em;border-radius:3px;font-size:.9em}"
        "pre{background:#f4f4f5;padding:.9rem 1rem;border-radius:6px;overflow-x:auto;"
        "font-size:.85em;line-height:1.5;margin:1rem 0}"
        "pre code{background:transparent;padding:0;border-radius:0;white-space:pre}"
        "h2{margin-top:2rem;border-bottom:1px solid #e5e5e5;padding-bottom:.3rem}"
        "li{margin:.35rem 0}hr{border:0;border-top:1px solid #e5e5e5;margin:2rem 0}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.92em}"
        "th,td{border:1px solid #e5e5e5;padding:.4rem .6rem;text-align:left}"
        "th{background:#f4f4f5;font-weight:600}"
        # the reference block: the handle for carrying this brief into a terminal
        ".ref{border:2px solid #2563eb;border-radius:10px;padding:.9rem 1.1rem;"
        "margin:0 0 2rem;background:#eff6ff}"
        ".ref-label{font-size:.75rem;letter-spacing:.06em;text-transform:uppercase;"
        "color:#2563eb;font-weight:600;margin-bottom:.5rem}"
        ".ref-row{display:flex;align-items:center;gap:.75rem;flex-wrap:wrap}"
        ".ref-code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"
        "font-size:1.5rem;font-weight:700;background:transparent;padding:0;"
        "color:#1e40af;user-select:all}"
        ".ref button{font:inherit;font-size:.85rem;padding:.35rem .9rem;cursor:pointer;"
        "border:1px solid #2563eb;border-radius:6px;background:#fff;color:#2563eb;"
        "font-weight:600;margin-left:auto}"
        ".ref button:hover{background:#2563eb;color:#fff}"
        ".ref button.ok{background:#16a34a;border-color:#16a34a;color:#fff}"
        "@media(prefers-color-scheme:dark){body{background:#1a1a1a;color:#e8e8e8}"
        "code{background:#2d2d30}h2{border-color:#333}hr{border-color:#333}"
        "pre{background:#242426}pre code{background:transparent}"
        "th,td{border-color:#333}th{background:#242426}"
        ".ref{background:#11213d;border-color:#3b82f6}"
        ".ref-label{color:#7dabff}.ref-code{color:#bfdbfe}"
        ".ref button{background:transparent;border-color:#3b82f6;color:#7dabff}"
        ".ref button:hover{background:#3b82f6;color:#fff}}"
        "</style></head><body>" + ref + md_to_html(md) + "</body></html>"
    )
    return out


def notify_macos(summary: dict, html: pathlib.Path, bid: int | None,
                 open_brief: bool, dry: bool) -> None:
    c = summary["counts"]
    title = f"☀️ Morning Brief #{bid}" if bid else "☀️ Morning Brief"
    subtitle = f"{c['drafts']} to draft · {c['asks']} asks · {c['your_turn']} your turn"
    body = clip(summary["top"], 180)

    def osa(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = (f'display notification "{osa(body)}" '
              f'with title "{osa(title)}" subtitle "{osa(subtitle)}" sound name "Glass"')
    if dry:
        print(f"[dry-run] osascript: {script}")
        print(f"[dry-run] would open: {html}")
        return
    try:
        subprocess.run(["osascript", "-e", script], check=True,
                       capture_output=True, text=True, timeout=20)
    except subprocess.CalledProcessError as e:
        die(3, f"osascript failed: {e.stderr.strip() or e}")
    except (OSError, subprocess.SubprocessError) as e:
        die(3, f"could not send the macOS notification: {e}")
    if open_brief:
        # -g opens without stealing focus, so a 07:52 run does not hijack the screen.
        # The return code is checked: half a delivery reported as a whole one is the
        # exact dishonesty this script exists to avoid. The receipt records that the
        # notification itself did land, so the failure stays diagnosable.
        try:
            r = subprocess.run(["open", "-g", str(html)],
                               capture_output=True, text=True, timeout=20)
        except (OSError, subprocess.SubprocessError) as e:
            die(3, f"notification sent, but the brief page could not be opened: {e}",
                notification_sent=True)
        if r.returncode != 0:
            die(3, f"notification sent, but `open` failed (exit {r.returncode}): "
                   f"{r.stderr.strip() or html}", notification_sent=True)


def notify_mattermost(summary: dict, md: str, bid: int | None,
                      webhook: str, dry: bool) -> None:
    c = summary["counts"]
    head = (f"### ☀️ Morning Brief {'#' + str(bid) if bid else ''}\n"
            f"**{c['drafts']}** to draft · **{c['asks']}** asks · "
            f"**{c['your_turn']}** your turn\n\n"
            f"**Top of your list:** {summary['top']}\n\n---\n")
    # Mattermost rejects very long posts; keep the head guaranteed and clip the body.
    body = md if len(md) < 14000 else md[:14000] + "\n\n_(truncated, full brief in the repo)_"
    payload = json.dumps({"text": head + body}).encode()

    if dry:
        print(f"[dry-run] POST {webhook[:40]}... ({len(payload)} bytes)")
        return
    req = urllib.request.Request(webhook, data=payload,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                die(3, f"webhook returned HTTP {r.status}")
    except urllib.error.HTTPError as e:
        die(3, f"webhook rejected the post: HTTP {e.code} {e.read()[:200]!r}")
    except (urllib.error.URLError, OSError) as e:
        die(3, f"could not reach the webhook: {e}")


# `delivery.channel` was a config key nothing read. commands/morning.md says the
# brief goes to `delivery.channel`, but the invocation it ships passes only
# --brief and --date, and this script defaulted to macos. So an adopter who set
# `channel: file` got macos, and the receipt recorded macos while the config said
# file. That is a config describing coverage you do not have, in the delivery
# phase. Resolve it here too, so omitting --channel cannot silently change the
# channel, and say where the value came from.
CONFIG_CANDIDATES = (
    "{root}/morning/config.yml",
)


def config_channel(root: pathlib.Path) -> tuple[str | None, str | None]:
    """(channel, where it came from) from delivery.channel, or (None, None)."""
    env = os.environ.get("MORNING_CONFIG")
    cands = [pathlib.Path(env).expanduser()] if env else []
    user = (os.environ.get("USER") or "").lower()
    cands += [pathlib.Path(t.format(root=root, user=user)) for t in CONFIG_CANDIDATES]
    for c in cands:
        try:
            if not c.is_file():
                continue
            text = c.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        in_delivery = False
        for line in text.splitlines():
            if re.match(r"^delivery:", line):
                in_delivery = True
                continue
            if in_delivery:
                if re.match(r"^\S", line):
                    break
                m = re.match(r"\s+channel:\s*([a-z]+)", line)
                if m and m.group(1) in ("macos", "mattermost", "file"):
                    return m.group(1), str(c)
    return None, None


# --------------------------------------------------------------- main
def main() -> int:
    global RECEIPT

    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", required=True)
    ap.add_argument("--channel", default=None, choices=["macos", "slack", "mattermost", "file"],
                    help="overrides delivery.channel in the config. Omitted, the "
                         "config's value is used, then macos.")
    ap.add_argument("--date")
    ap.add_argument("--no-open", action="store_true", help="don't open the rendered brief")
    ap.add_argument("--no-notify", action="store_true",
                    help="render + write the receipt, but skip the OS notification and browser "
                         "open entirely (implies --no-open) — for a silent in-place brief update "
                         "after an initial delivery already happened this run, e.g. Phase 2p "
                         "landing pre-drafts. Still marks the receipt status 'sent'.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root", default=os.environ.get("MORNING_ROOT"),
                    help="artefact root. Overrides the layout probe; use it when the "
                         "receipts are not landing where your config points.")
    a = ap.parse_args()
    # The webhook comes from the environment only, never argv: the unattended run may call
    # this script, and a URL in its arguments could come from text it read in a source.
    a.webhook = os.environ.get("MORNING_SLACK_WEBHOOK") or os.environ.get("MORNING_MATTERMOST_WEBHOOK")

    configure_roots(a.root)

    # Channel precedence: --channel, then $MORNING_NOTIFY_CHANNEL, then the
    # config's delivery.channel, then macos. Recorded so a surprise is traceable.
    chan_src = "--channel"
    if a.channel is None:
        a.channel = os.environ.get("MORNING_NOTIFY_CHANNEL")
        chan_src = "$MORNING_NOTIFY_CHANNEL"
    if a.channel is None:
        a.channel, where = config_channel(REPO)
        chan_src = f"config {where}" if a.channel else chan_src
    if a.channel is None:
        a.channel, chan_src = "macos", "default (no config value found)"

    # Build the receipt FIRST, on the least information that makes it useful: a
    # date and where it will be written. Everything after this point can fail,
    # and from here on every one of those failures leaves an artifact behind.
    date = a.date or dt.date.today().isoformat()
    RECEIPT = {
        "date": date, "brief_id": None, "channel": a.channel,
        "root": str(REPO), "layout": LAYOUT,
        "brief_file": a.brief, "rendered": None,
        "subject": f"☀️ Morning Brief · {date}",
        "counts": None, "top": None,
        "sent_at": None, "message_id": None,
    }

    path = pathlib.Path(a.brief)
    if not path.is_absolute():
        path = REPO / path
    RECEIPT["brief_file"] = str(path)
    if not path.exists():
        die(2, f"brief file not found: {path}")
    # Only a brief is ever sent: a .md file in the briefs folder, never any other file.
    briefs = RENDER_DIR.parent.resolve()
    if path.suffix != ".md" or not path.resolve().is_relative_to(briefs):
        die(2, f"--brief must be a .md file in {briefs}")
    md = path.read_text()
    if not md.strip():
        die(2, f"brief file is empty: {path}")

    bid = assign_id(load_index(), date, str(path), f"Morning Brief {date}")
    summary = summarise(md)
    html = render_html(md, date, bid)

    RECEIPT |= {
        "brief_id": bid, "rendered": str(html),
        "subject": f"☀️ Morning Brief #{bid} · {date}",
        "counts": summary["counts"], "top": summary["top"],
    }

    if a.no_notify:
        pass  # render_html + write_receipt above/below already ran; no OS ping, no browser open
    elif a.channel == "macos":
        notify_macos(summary, html, bid, not a.no_open, a.dry_run)
    elif a.channel in ("slack", "mattermost"):   # both take the same {"text": ...} incoming-webhook payload
        if not a.webhook:
            die(2, "no webhook. Set MORNING_SLACK_WEBHOOK (or MORNING_MATTERMOST_WEBHOOK) in the environment.")
        notify_mattermost(summary, md, bid, a.webhook, a.dry_run)

    # `file` renders a page and delivers nothing, so it must not claim `sent`.
    # A receipt that says "sent" for a channel that sent nothing is how a brief
    # nobody ever saw gets counted as a delivered one.
    if a.dry_run:
        status, delivered = "dry_run", False
    elif a.channel == "file":
        status, delivered = "rendered_not_sent", False
    else:
        status, delivered = "sent", True

    write_receipt(RECEIPT | {
        "status": status,
        "sent_at": (dt.datetime.now().astimezone().isoformat(timespec="seconds")
                    if delivered else None),
        # When the page was made, sent or not. ontime.py counts a `file`-channel
        # day as delivered and needs a time to measure it by; without this every
        # such day read as "missed" (runner port, 2026-10-05).
        "rendered_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    })
    if delivered:
        verb = f"delivered via {a.channel}"
    elif a.dry_run:
        verb = f"rendered, send only DESCRIBED (dry run, {a.channel})"
    else:
        verb = f"rendered, NOT delivered ({a.channel})"
    print(f"notify: brief #{bid} for {date} {verb} "
          f"({summary['counts']['drafts']} to draft, {summary['counts']['asks']} asks, "
          f"{summary['counts']['your_turn']} your turn)")
    print(f"        root:     {REPO}  [{LAYOUT} layout]")
    print(f"        rendered: {html}")
    print(f"        receipt:  {RECEIPTS / (date + '.json')}")
    return 0


if __name__ == "__main__":
    # The receipt promise has to survive the paths nobody wrote on purpose too:
    # an unhandled exception and a watchdog's Ctrl-C both used to leave nothing
    # at all, which reads downstream as "never attempted".
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        record_failure("interrupted before delivery finished")
        raise SystemExit(130)
    except BaseException as e:
        record_failure(f"unexpected {type(e).__name__}: {e}")
        raise
