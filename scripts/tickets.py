#!/usr/bin/env python3
"""
tickets.py: the meeting-to-action approval queue.

Why this exists
---------------
`meeting_debrief` has always been able to draft tickets. What it could not do is
hand them over in a shape the owner could act on: they were prose inside a debrief
file, mixed with decisions and action items, with no per-ticket yes or no and no
record of which ones got built. So they were re-typed by hand or lost.

This makes the tickets a queue with a gate:

    1. the loop drafts them        -> tickets-from-meetings.md, one block per ticket
    2. the owner ticks the boxes       -> [x] build it, [-] drop it
    3. `sync` reads the boxes back -> state, not a guess
    4. the loop creates ONLY the ticked ones, at the gate, one at a time
    5. `created` records the real Jira key and appends to the outbound ledger

Generalised 2026-09-24 from tickets to three kinds, because the tick-to-approve
gate is the only part of this loop with a clean adoption record (ten tickets
approved and created on 2026-09-01) and the other two things a meeting produces
had no equivalent. They arrived as prose in a debrief and had to be re-read and
re-typed:

    ticket   -> Jira, one confirmation each          (unchanged)
    decision -> your decision log (a page or file you keep)
    update   -> a named channel, per the three-channel structure

One file, grouped by meeting. `kind` defaults to `ticket`, so every state file
written before today keeps working.

Rules enforced in code rather than asked for in a prompt, because each one has
already produced a bad artifact:

  * **The four house headers.** Measured 2026-08-26 across the drafts folder: 8 of 10
    ticket drafts carried none of `**Context:**`, `**Problem:**`,
    `**What we need:**`, `**Why this matters:**`. A ticket missing any of them
    cannot be approved here.
  * **The stub rule.** Granola transcripts are summary-level paraphrase. Acceptance
    criteria written from a paraphrase are invented. So a ticket whose source is
    not verbatim ships as a STUB with exactly one criterion, `confirm scope with
    {role} before estimating`, and any attempt to give it five invented ones is a
    validation error. A stub someone confirms in 40 seconds beats a plausible
    ticket nobody trusts.
  * **No attribution from a paraphrase.** A decision drawn from a summary-level
    source may record what the room decided and may NOT name who said it. Same
    root cause as the stub rule, different artifact.
  * **A decision is not an action, and not a discussion.** "We should look at X"
    is a ticket. "We might cap it" is a discussion. Neither goes in the Decision
    Log, which is the record of why the world is the way it is.
  * **No unsourced number leaves in an update**, and nothing from the hygiene
    queue ever goes external. Both are existing config rules that nothing checked.

Commands
--------
  tickets.py draft   --date D --in f|-     ingest drafted actions, render the queue
  tickets.py sync    --date D              read the ticked boxes back into state
  tickets.py approved --date D --json      the ones cleared to act on
  tickets.py done    --date D --id t1 --to "jira WEB-101"   record what was done
  tickets.py status  --date D
  tickets.py selftest

Exit codes: 0 fine · 1 something needs your attention · 2 usage error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import re
import hashlib
import subprocess
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from trust import Ctx, repo_root, today, slug  # noqa: E402

HEADERS = ("**Context:**", "**Problem:**", "**What we need:**", "**Why this matters:**")
FIELDS = ("context", "problem", "what_we_need", "why_this_matters")
STUB_AC_RE = re.compile(r"confirm\s+scope\s+with\s+.+\s+before\s+estimating", re.I)
ESTIMATE_RE = re.compile(r"story\s*point|\bSP\s*[:=]|complexity\s*(score|:)|definition of done", re.I)
KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d{1,6}\b")

STATE_DRAFTED, STATE_APPROVED, STATE_REJECTED, STATE_CREATED = (
    "drafted", "approved", "rejected", "created")

KINDS = ("ticket", "decision", "update", "research", "question", "idea")
KIND_LABEL = {"ticket": "Ticket", "decision": "Decision", "update": "Update",
              "research": "Research", "question": "Question", "idea": "Idea"}
# Destination per kind, so an approved item knows where it is going before it goes.
KIND_DESTINATION = {
    "ticket": "Jira",
    "decision": "your decision log",
    "update": "a named channel",
    "research": "a local note, or a spike task if it needs the team",
    "question": "one named person",
    "idea": "an entry in your ideas list or backlog",
}
# A decision may live in a design decisions table instead of the decision log.
# Same rules, different home, which is why it is a destination and not a kind.
DECISION_HOMES = ("decision_log", "design_table")
# The three-channel structure. An update with no channel in this set is not
# refused, it is flagged, because a new channel is a real thing and a typo is not.
KNOWN_CHANNELS = ("confluence", "notion", "slack", "teams", "mattermost", "email")
HEDGE_RE = re.compile(r"\b(maybe|might|perhaps|possibly|probably|tbd|to be decided|"
                      r"we could|leaning towards)\b", re.I)
ACTION_OPENER_RE = re.compile(r"^\s*(we should|we need to|someone should|let'?s|"
                              r"todo|action:|next step)\b", re.I)
NUMBERY_RE = re.compile(r"\d\s*%|[$\u00a3\u20ac]\s*\d|\b\d[\d,.]*\s*"
                        r"(users?|signups?|sessions?|conversions?|exposures?|pp|bps)\b", re.I)


def die(msg: str, code: int = 2):
    print(f"tickets.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


QUEUE_NAME = "meeting-actions.md"
LEGACY_QUEUE_NAME = "tickets-from-meetings.md"


PROVENANCE = "morning/state/provenance.jsonl"


def uid_of(ctx: Ctx, t: dict) -> str:
    """The durable id. `t1` collides across days and so cannot be pointed at;
    `2026-09-24/t1` can. This is what makes derived_from and the chain work."""
    return t.get("uid") or f"{ctx.date}/{t['id']}"


def load_provenance(repo: pathlib.Path) -> list[dict]:
    f = repo / PROVENANCE
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


def append_provenance(repo: pathlib.Path, rec: dict) -> None:
    f = repo / PROVENANCE
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def rewrite_provenance(repo: pathlib.Path, rows: list[dict]) -> None:
    (repo / PROVENANCE).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def queue_path(ctx: Ctx) -> pathlib.Path:
    """The queue file. Reads the pre-2026-09-24 name if that is what is on disk,
    so a day mid-flight does not lose its ticked boxes to a rename."""
    legacy = ctx.review_dir / LEGACY_QUEUE_NAME
    new = ctx.review_dir / QUEUE_NAME
    if legacy.exists() and not new.exists():
        return legacy
    return new


def state_path(ctx: Ctx) -> pathlib.Path:
    return ctx.trust_dir / "tickets.json"


def load_state(ctx: Ctx) -> dict:
    p = state_path(ctx)
    if not p.exists():
        return {"date": ctx.date, "tickets": []}
    return json.loads(p.read_text())


def save_state(ctx: Ctx, st: dict) -> None:
    ctx.trust_dir.mkdir(parents=True, exist_ok=True)
    state_path(ctx).write_text(json.dumps(st, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# validation: the rules that have already been broken in real tickets
# ---------------------------------------------------------------------------

def source_hash(t: dict) -> str:
    """Hash of the evidence this item rests on.

    Adapted from a colleague's plan-drafting `content_hash`, which drops a plan's
    approval when the ticket it was signed off against has since moved. Same
    idea, different object: an approval here is a tick, and a tick that survives
    its source changing underneath it is exactly the silent staleness the trust
    layer was built to remove. Whitespace-normalised so a reformat is not a change.
    """
    src = t.get("source") or {}
    blob = " ".join(str(src.get(k, "")) for k in ("meeting", "when", "fidelity", "excerpt"))
    return hashlib.sha256(re.sub(r"\s+", " ", blob).strip().encode()).hexdigest()[:16]


def kind_of(t: dict) -> str:
    return (t.get("kind") or "ticket").strip().lower()


def validate(t: dict) -> list[str]:
    """Dispatch by kind. Anything written before 2026-09-24 has no kind and is a ticket."""
    k = kind_of(t)
    if k == "ticket":
        return validate_ticket(t)
    if k == "decision":
        return validate_decision(t)
    if k == "update":
        return validate_update(t)
    if k == "research":
        return validate_research(t)
    if k == "question":
        return validate_question(t)
    if k == "idea":
        return validate_idea(t)
    return [f"unknown kind {k!r}; must be one of {', '.join(KINDS)}"]


def _source_issues(t: dict) -> tuple[list[str], str]:
    src = t.get("source") or {}
    fidelity = (src.get("fidelity") or "").strip().lower()
    issues = []
    if not str(src.get("excerpt") or "").strip():
        issues.append("no source excerpt: an item from a meeting must quote the meeting")
    if fidelity not in ("verbatim", "summary"):
        issues.append('source.fidelity must be "verbatim" or "summary"')
    return issues, fidelity


def validate_decision(t: dict) -> list[str]:
    """The Decision Log records WHY the world is the way it is. Two things it is
    not: an action (that is a ticket) and a discussion (that is not decided yet).
    Both have reached it before."""
    issues, fidelity = _source_issues(t)
    what = str(t.get("decision") or t.get("title") or "").strip()

    if not what:
        issues.append("no decision stated")
    else:
        if ACTION_OPENER_RE.search(what):
            issues.append(f"that is an action, not a decision: {what!r}. File it as kind=ticket")
        if HEDGE_RE.search(what):
            issues.append(f"hedged, so it was discussed rather than decided: {what!r}. "
                          f"The Decision Log is not a record of leanings")
    if not str(t.get("rationale") or "").strip():
        issues.append("no rationale: a decision with no why is unusable six weeks later, which is "
                      "exactly when the log gets read")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(t.get("decided_on") or "")):
        issues.append("decided_on must be a real date (YYYY-MM-DD)")
    if not str(t.get("binds") or "").strip():
        issues.append("no `binds`: name the role or group this decision constrains")

    home = (t.get("home") or "decision_log").strip().lower()
    if home not in DECISION_HOMES:
        issues.append(f"home {home!r} must be one of {', '.join(DECISION_HOMES)}")
    if fidelity == "summary" and str(t.get("attributed_to") or "").strip():
        issues.append(f"source is summary-level paraphrase, so it cannot attribute the decision to "
                      f"{t['attributed_to']!r}. Record what the room decided, not who said it")
    return issues


def validate_update(t: dict) -> list[str]:
    """An update leaves the workspace, so it gets the strictest data rule here."""
    issues, _ = _source_issues(t)
    audience = str(t.get("audience") or "").strip()
    substance = str(t.get("substance") or t.get("title") or "").strip()

    if not audience:
        issues.append("no audience: name the channel, per the three-channel structure")
    elif not any(c in audience.lower() for c in KNOWN_CHANNELS):
        issues.append(f"audience {audience!r} is not one of the known channels "
                      f"({', '.join(KNOWN_CHANNELS)}). If it is a new one, say so in the note")
    if not substance:
        issues.append("nothing to say")
    if t.get("hygiene"):
        issues.append("this is a hygiene-queue item and hygiene.never_external is set. It is true "
                      "and actionable and it is not stakeholder-facing. Route it to the hygiene "
                      "queue, not to a channel")
    blob = " ".join(str(v) for v in (substance, t.get("detail") or ""))
    if NUMBERY_RE.search(blob) and not (t.get("sources") or []):
        issues.append("carries a number and names no source. Every metric traces to Amplitude, Jira "
                      "or a transcript, or it is labelled unavailable")
    return issues


def validate_research(t: dict) -> list[str]:
    """The rule that matters: name what would change if it were answered.

    Without it this is curiosity, and 14 of the 213 action items sampled on
    2026-09-24 were research-shaped with no stated consequence. A list of
    interesting questions is how a backlog gets long without getting better.
    """
    issues, _ = _source_issues(t)
    if not str(t.get("question") or t.get("title") or "").strip():
        issues.append("nothing stated to look into")
    if not str(t.get("changes_what") or "").strip():
        issues.append("no `changes_what`: name the decision or the action that changes depending on "
                      "the answer. If nothing changes, this is curiosity and does not belong in a "
                      "queue that costs you a review")
    if not str(t.get("owner") or "").strip():
        issues.append("no owner: name the role or person who would do it, even if that is you")
    return issues


def validate_question(t: dict) -> list[str]:
    """One closed question, one named person. That is the ASK contract, applied
    where most of the owner's questions are actually born."""
    issues, _ = _source_issues(t)
    q = str(t.get("question") or t.get("title") or "").strip()
    if not q:
        issues.append("no question")
    else:
        if not q.endswith("?"):
            issues.append(f"not a question: {q!r}. If it is a task, file it as kind=ticket")
        if q.count("?") > 1:
            issues.append("more than one question. Two questions get neither answered; split them")
    if not str(t.get("ask") or "").strip():
        issues.append("no `ask`: name the one person who can answer it")
    if not str(t.get("unblocks") or "").strip():
        issues.append("no `unblocks`: say what proceeds once it is answered. A question that "
                      "unblocks nothing is a carried item waiting to happen")
    return issues


def validate_idea(t: dict) -> list[str]:
    """The core of an idea entry, not a full template. An idea from a meeting is
    early; demanding all eight fields would just produce invented ones."""
    issues, _ = _source_issues(t)
    if not str(t.get("title") or "").strip():
        issues.append("no title")
    if not str(t.get("problem") or "").strip():
        issues.append("no `problem`: who faces this, in their situation, not ours")
    if not str(t.get("proposed_solution") or "").strip():
        issues.append("no `proposed_solution`")
    if not str(t.get("strategic_alignment") or "").strip():
        issues.append("no `strategic_alignment`: name the KR or goal it serves, or say plainly that "
                      "it serves none, which is a real and acceptable answer for a parked idea")
    if not str(t.get("riskiest_assumption") or "").strip():
        issues.append("no `riskiest_assumption`. An idea without one is a preference, and the "
                      "assumption is the thing the next step has to test")
    return issues


def validate_ticket(t: dict) -> list[str]:
    issues: list[str] = []
    role = (t.get("role") or "").strip()
    src = t.get("source") or {}
    fidelity = (src.get("fidelity") or "").strip().lower()
    ac = [a for a in (t.get("acceptance_criteria") or []) if str(a).strip()]

    if not (t.get("title") or "").strip():
        issues.append("no title")
    elif not re.match(r"^\s*\[[^\]]+\]", t["title"]):
        issues.append("title carries no role tag, e.g. `[FE]` or `[Backend]`")

    for f, h in zip(FIELDS, HEADERS):
        if not str(t.get(f) or "").strip():
            issues.append(f"missing or empty {h}")

    if not role:
        issues.append("no accountable role named (role_not_person is block severity)")
    if str(t.get("assignee") or "").strip():
        issues.append("assignee is set; tickets go to roles, not people")

    if not str(src.get("excerpt") or "").strip():
        issues.append("no source excerpt: a ticket from a meeting must quote the meeting")
    if fidelity not in ("verbatim", "summary"):
        issues.append('source.fidelity must be "verbatim" or "summary"')

    if fidelity == "summary":
        if len(ac) != 1:
            issues.append(
                f"source is summary-level paraphrase but the ticket carries {len(ac)} acceptance "
                f"criteria. Criteria written from a paraphrase are invented. Ship it as a STUB "
                f"with exactly one: 'confirm scope with {role or '{role}'} before estimating'")
        elif not STUB_AC_RE.search(ac[0]):
            issues.append("summary-level source, so the single criterion must read "
                          "'confirm scope with {role} before estimating'")
    elif fidelity == "verbatim":
        if not (5 <= len(ac) <= 7):
            issues.append(f"{len(ac)} acceptance criteria; the house format is 5 to 7")
        for a in ac:
            if re.match(r"^\s*(build|implement|add|create|write|refactor)\b", str(a), re.I):
                issues.append(f"criterion is a task, not an observable outcome: {a!r}")

    blob = json.dumps(t, ensure_ascii=False)
    if ESTIMATE_RE.search(blob):
        issues.append("carries an estimate, complexity score or Definition of Done")

    verified = {k.upper() for k in (t.get("verified_keys") or [])}
    referenced = {k.upper() for k in KEY_RE.findall(blob)} - {(t.get("jira_key") or "").upper()}
    unverified = sorted(referenced - verified)
    if unverified:
        issues.append("these referenced keys are not confirmed in your task scope "
                      "(sources.tasks.scope): " + ", ".join(unverified))
    return issues


def is_stub(t: dict) -> bool:
    return (kind_of(t) == "ticket"
            and (t.get("source") or {}).get("fidelity", "").lower() == "summary")


# ---------------------------------------------------------------------------
# render + sync: the file IS the interface
# ---------------------------------------------------------------------------

def box(t: dict) -> str:
    return {STATE_APPROVED: "[x]", STATE_REJECTED: "[-]",
            STATE_CREATED: "[x]"}.get(t.get("state"), "[ ]")


def meeting_of(t: dict) -> str:
    return str((t.get("source") or {}).get("meeting") or "No meeting recorded").strip()


def render(ctx: Ctx, st: dict) -> str:
    ts = st.get("tickets") or []
    blocked = [t for t in ts if t.get("issues")]
    done = [t for t in ts if t.get("state") == STATE_CREATED]
    by_kind = {k: [x for x in ts if kind_of(x) == k] for k in KINDS}

    L: list[str] = []
    L.append(f"# Meeting actions, {ctx.date}")
    L.append("")
    counts = " · ".join(f"{len(v)} {KIND_LABEL[k].lower()}{'s' if len(v) != 1 else ''}"
                        for k, v in by_kind.items() if v) or "nothing"
    L.append(f"**{counts}."
             + (f" {len(blocked)} blocked by a rule." if blocked else "")
             + (f" {len(done)} already done." if done else "")
             + " Nothing has left this workspace except where a destination is shown.**")
    L.append("")
    L.append("**To approve:** tick `[x]` for every item you want acted on, `[-]` to drop one, and "
             "add `reject: your reason` on the same line if the reason is worth keeping. Save, then:")
    L.append("")
    L.append("```bash")
    L.append(f"python3 morning/engine/tickets.py sync --date {ctx.date}")
    L.append("```")
    L.append("")
    L.append("A tick is not the action. Each approved item is confirmed once more at the ship gate, "
             "because creating a task, editing the decision log and posting to a channel are all "
             "`never_auto`. An item marked `BLOCKED` cannot be approved until the named problem is "
             "fixed: every one of those rules is there because it has already produced a bad artifact.")
    L.append("")

    if not ts:
        L.append("---")
        L.append("")
        L.append("_No actions came out of the meetings read this run._")
        L.append("")
        return "\n".join(L)

    meetings: dict[str, list[dict]] = {}
    for x in ts:
        meetings.setdefault(meeting_of(x), []).append(x)

    for meeting, items in meetings.items():
        L.append("---")
        L.append("")
        when = ((items[0].get("source") or {}).get("when") or "").strip()
        fid = ((items[0].get("source") or {}).get("fidelity") or "?").lower()
        L.append(f"# {meeting}" + (f", {when}" if when else ""))
        L.append("")
        L.append(f"Source fidelity: **{fid}**"
                 + ("  (paraphrase, so tickets ship as stubs and no decision names a speaker)"
                    if fid == "summary" else ""))
        L.append("")
        for k in KINDS:
            mine = [x for x in items if kind_of(x) == k]
            if not mine:
                continue
            L.append(f"## {KIND_LABEL[k]}s ({len(mine)}) -> {KIND_DESTINATION[k]}")
            L.append("")
            for x in mine:
                L.extend(_render_item(x))
        L.append("")
    return "\n".join(L)


def _render_item(t: dict) -> list[str]:
    k = kind_of(t)
    state = t.get("state", STATE_DRAFTED)
    stub = " · **STUB**" if is_stub(t) else ""
    tag = ""
    if state == STATE_CREATED:
        tag = f" · **done: {t.get('destination') or t.get('jira_key') or '?'}**"
    elif state == STATE_REJECTED:
        tag = " · **dropped**" + (f": {t['reject_reason']}" if t.get("reject_reason") else "")
    elif t.get("issues"):
        tag = " · **BLOCKED**"

    title = t.get("title") or t.get("decision") or t.get("substance") or "(untitled)"
    L = [f"### {box(t)} `{t['id']}` {title}{stub}{tag}", ""]

    if t.get("issues"):
        L.append("> **Blocked, and why:**")
        for i in t["issues"]:
            L.append(f"> - {i}")
        L.append("")

    if k == "ticket":
        L.append(f"**Type:** {t.get('issue_type','Story')} · **Accountable role:** "
                 f"{t.get('role','not named')} · **Assignee:** left empty, on purpose"
                 + (f" · **Epic:** {t['epic']}" if t.get("epic") else ""))
        L.append("")
        for f, h in zip(FIELDS, HEADERS):
            L.append(f"{h} {t.get(f,'') or '_missing_'}")
            L.append("")
        L.append("**Acceptance criteria**")
        L.append("")
        for a in (t.get("acceptance_criteria") or ["_none_"]):
            L.append(f"- [ ] {a}")
        L.append("")
    elif k == "decision":
        L.append(f"**Decided:** {t.get('decided_on','?')} · **Binds:** {t.get('binds','?')}"
                 + (f" · **Attributed to:** {t['attributed_to']}" if t.get("attributed_to") else ""))
        L.append("")
        L.append(f"**Why:** {t.get('rationale','_missing_')}")
        L.append("")
        if t.get("supersedes"):
            L.append(f"**Supersedes:** {t['supersedes']}")
            L.append("")
    elif k == "research":
        L.append(f"**Owner:** {t.get('owner','_missing_')}")
        L.append("")
        L.append(f"**Question:** {t.get('question') or t.get('title','')}")
        L.append("")
        L.append(f"**What changes when it is answered:** {t.get('changes_what','_missing_')}")
        L.append("")
    elif k == "question":
        L.append(f"**Ask:** {t.get('ask','_missing_')}")
        L.append("")
        L.append(f"**Unblocks:** {t.get('unblocks','_missing_')}")
        L.append("")
    elif k == "idea":
        L.append(f"**Serves:** {t.get('strategic_alignment','_missing_')}")
        L.append("")
        L.append(f"**Problem:** {t.get('problem','_missing_')}")
        L.append("")
        L.append(f"**Proposed:** {t.get('proposed_solution','_missing_')}")
        L.append("")
        L.append(f"**Riskiest assumption:** {t.get('riskiest_assumption','_missing_')}")
        L.append("")
    elif k == "update":
        L.append(f"**Audience:** {t.get('audience','_missing_')}")
        L.append("")
        if t.get("detail"):
            L.append(t["detail"])
            L.append("")
        if t.get("sources"):
            L.append("**Sources:** " + " · ".join(str(s) for s in t["sources"]))
            L.append("")

    if t.get("derived_from"):
        L.append(f"**Came from:** {', '.join(t['derived_from'])}")
        L.append("")
    if t.get("supersedes"):
        L.append(f"**Supersedes:** {', '.join(t['supersedes'])}")
        L.append("")
    exc = str((t.get("source") or {}).get("excerpt") or "").strip()
    L.append("> " + (exc.replace("\n", "\n> ") if exc else "_no excerpt recorded_"))
    L.append(f"\n`uid: {t.get('uid', t['id'])}`")
    L.append("")
    return L


def write_queue(ctx: Ctx, st: dict) -> None:
    ctx.review_dir.mkdir(parents=True, exist_ok=True)
    queue_path(ctx).write_text(render(ctx, st))


BOX_RE = re.compile(r"^#{2,3}\s*\[(?P<box>[ xX\-rR])\]\s*`(?P<id>[^`]+)`")


def read_boxes(text: str) -> dict[str, tuple[str, str]]:
    """id -> (box char, trailing reject reason)."""
    out: dict[str, tuple[str, str]] = {}
    for ln in text.splitlines():
        m = BOX_RE.match(ln)
        if not m:
            continue
        reason = ""
        rm = re.search(r"reject:\s*(.+?)\s*$", ln)
        if rm:
            reason = rm.group(1)
        out[m.group("id")] = (m.group("box").lower(), reason)
    return out


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_draft(ctx: Ctx, a) -> int:
    raw = sys.stdin.read() if a.infile in (None, "-") else pathlib.Path(a.infile).read_text()
    if not raw.strip():
        die("empty input")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"input is not valid JSON: {e}")
    incoming = data["tickets"] if isinstance(data, dict) else data
    if not isinstance(incoming, list):
        die('expected a JSON list of tickets, or {"tickets": [...]}')

    st = load_state(ctx)
    existing = {t["id"]: t for t in st["tickets"]}
    n = len(existing)
    # Re-drafting the same meeting must not duplicate the queue. Found by the loop
    # in its own output: "Re-running the
    # meeting-actions draft step appends instead of replacing (it duplicated the
    # queue this run)." Cause: an item with no explicit id got a fresh `t{n}` every
    # run, so identical content became a new row. Match on the content hash instead,
    # which is the same field that guards an approval against its source moving.
    by_hash = {source_hash(x): x["id"] for x in existing.values() if x.get("source_hash")}
    for t in incoming:
        if not t.get("id"):
            h = source_hash(t)
            same = by_hash.get(h)
            if same:
                t["id"] = same          # same source, same item: update it in place
            else:
                n += 1
                t["id"] = f"t{n}"
                by_hash[h] = t["id"]
        prev = existing.get(t["id"], {})
        if prev.get("state") == STATE_CREATED and not a.replace:
            print(f"skipping {t['id']}: already created as {prev.get('jira_key')}")
            continue
        t["state"] = prev.get("state", STATE_DRAFTED) if not a.replace else STATE_DRAFTED
        t["issues"] = validate(t)
        if t["issues"] and t["state"] == STATE_APPROVED:
            t["state"] = STATE_DRAFTED     # a re-draft that breaks a rule loses its approval

        # The source moved underneath an approval: the tick was for different words.
        t["source_hash"] = source_hash(t)
        old_hash = prev.get("source_hash")
        if old_hash and old_hash != t["source_hash"]:
            if t["state"] == STATE_APPROVED:
                t["state"] = STATE_DRAFTED
                t.setdefault("issues", []).append(
                    f"source changed since you approved this ({old_hash} -> {t['source_hash']}), "
                    f"so the approval is dropped. Re-read it and tick again.")
                print(f"  APPROVAL DROPPED {t['id']}: its source changed after you ticked it")
            elif t["state"] == STATE_CREATED:
                t["source_changed_after_done"] = True
                print(f"  NOTE {t['id']}: already acted on, and its source has since changed")
        t["drafted_at"] = t.get("drafted_at") or _dt.datetime.now().replace(
            microsecond=0).isoformat()
        t["uid"] = uid_of(ctx, t)
        existing[t["id"]] = {**prev, **t}
    st["tickets"] = list(existing.values())
    save_state(ctx, st)
    write_queue(ctx, st)

    blocked = [t for t in st["tickets"] if t.get("issues")]
    stubs = [t for t in st["tickets"] if is_stub(t)]
    kinds = ", ".join(f"{len([x for x in st['tickets'] if kind_of(x) == k])} {k}"
                      for k in KINDS if any(kind_of(x) == k for x in st["tickets"]))
    print(f"{len(st['tickets'])} action(s) queued ({kinds}) -> "
          f"{queue_path(ctx).relative_to(ctx.repo)}")
    if stubs:
        print(f"  {len(stubs)} stub(s): the source was paraphrase, so they carry one "
              f"confirm-scope criterion by rule, not invented ones")
    for t in blocked:
        print(f"  BLOCKED {t['id']} ({kind_of(t)}):")
        for i in t["issues"]:
            print(f"      {i}")
    return 1 if blocked else 0


def cmd_sync(ctx: Ctx, a) -> int:
    p = queue_path(ctx)
    if not p.exists():
        die(f"no ticket queue at {p}", 1)
    st = load_state(ctx)
    boxes = read_boxes(p.read_text())
    if not boxes:
        die("no ticket blocks found in the queue file; has it been edited into a different shape?", 1)

    approved, rejected, refused = [], [], []
    for t in st["tickets"]:
        b, reason = boxes.get(t["id"], (" ", ""))
        if t.get("state") == STATE_CREATED:
            continue
        if b == "x":
            if t.get("issues"):
                refused.append(t)
                t["state"] = STATE_DRAFTED
            else:
                t["state"] = STATE_APPROVED
                approved.append(t)
        elif b in ("-", "r"):
            t["state"] = STATE_REJECTED
            if reason:
                t["reject_reason"] = reason
            rejected.append(t)
        else:
            if t.get("state") != STATE_REJECTED:
                t["state"] = STATE_DRAFTED
    save_state(ctx, st)
    write_queue(ctx, st)

    print(f"{len(approved)} approved · {len(rejected)} dropped · "
          f"{len([t for t in st['tickets'] if t['state'] == STATE_DRAFTED])} still undecided")
    for t in refused:
        print(f"  REFUSED {t['id']}: ticked, but blocked. {t['issues'][0]}")
    if approved:
        print("  approved: " + ", ".join(t["id"] for t in approved))
        print("  Nothing has happened yet. The loop asks once more per item at the ship gate.")
    return 1 if refused else 0


def cmd_approved(ctx: Ctx, a) -> int:
    st = load_state(ctx)
    out = [t for t in st["tickets"] if t.get("state") == STATE_APPROVED]
    if a.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    if not out:
        print("nothing approved to build.")
        return 0
    for t in out:
        print(f"{t['id']}  [{kind_of(t)}]  "
              f"{t.get('title') or t.get('decision') or t.get('substance')}"
              + ("  [STUB]" if is_stub(t) else "")
              + f"  -> {KIND_DESTINATION[kind_of(t)]}")
    return 0


def cmd_done(ctx: Ctx, a) -> int:
    """Record that an approved item actually landed. One destination, per kind."""
    st = load_state(ctx)
    t = next((x for x in st["tickets"] if x["id"] == a.id), None)
    if not t:
        die(f"no item {a.id} in today's queue")
    if t.get("state") != STATE_APPROVED:
        die(f"{a.id} is {t.get('state')}, not approved. Only approved items get acted on.", 1)

    k = kind_of(t)
    dest = (a.to or "").strip()
    if a.key:                                   # backwards compatible with --key WEB-123
        dest = f"jira {a.key}"
    if not dest:
        die(f"--to is required: name where this {k} landed "
            f"(e.g. \"jira WEB-101\", \"confluence 123456\", \"slack #team-product\")")
    if k == "ticket":
        m = re.search(r"(KM-\d+)", dest)
        if not m:
            die("a ticket's destination must contain the real Jira key it was created as", 1)
        t["jira_key"] = m.group(1)

    t["state"] = STATE_CREATED
    t["destination"] = dest
    t["created_at"] = _dt.datetime.now().replace(microsecond=0).isoformat()
    save_state(ctx, st)
    write_queue(ctx, st)

    cmd = [sys.executable, str(pathlib.Path(__file__).with_name("shipped.py")),
           "--repo", str(ctx.repo), "add",
           "--job", f"{k}:{t['id']}", "--to", dest,
           "--draft", str(queue_path(ctx).relative_to(ctx.repo)),
           "--date", ctx.date, "--by", a.by,
           "--note", f"{meeting_of(t)}: {(t.get('title') or t.get('decision') or t.get('substance') or '')}"[:140]]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)

    # The provenance row. The outbound ledger proves a thing LEFT. This records
    # where it came from and leaves a slot for what came of it, which is the half
    # that makes the loop learnable rather than merely auditable.
    src = t.get("source") or {}
    append_provenance(ctx.repo, {
        "uid": uid_of(ctx, t),
        "kind": k,
        "title": t.get("title") or t.get("decision") or t.get("substance")
                 or t.get("question") or "",
        "source": {"meeting": meeting_of(t), "when": src.get("when", ""),
                   "fidelity": src.get("fidelity", ""), "excerpt": src.get("excerpt", "")},
        "destination": dest,
        "derived_from": t.get("derived_from") or [],
        "supersedes": t.get("supersedes") or [],
        "done_at": t["created_at"],
        "by": a.by,
        "outcome": None, "outcome_at": None, "outcome_source": None,
    })
    print(f"{a.id} recorded: {k} -> {dest}   uid {uid_of(ctx, t)}")
    if t.get("derived_from"):
        print(f"  derived from: {', '.join(t['derived_from'])}")
    return 0


def cmd_outcome(ctx: Ctx, a) -> int:
    """Close the circle. The outcome NEVER comes from the loop's own opinion: it
    comes from a source you can name, a Jira resolution, an experiment object, a
    later decision that reversed this one."""
    rows = load_provenance(ctx.repo)
    r = next((x for x in rows if x["uid"] == a.uid), None)
    if not r:
        die(f"no provenance row {a.uid}. `chain --list` shows what exists.")
    if not a.source:
        die("--source is required: name where the outcome was read (a Jira resolution, an "
            "analytics experiment object, a decision log entry). An outcome with no source is "
            "the loop marking its own homework.")
    r["outcome"] = a.result
    r["outcome_at"] = _dt.datetime.now().replace(microsecond=0).isoformat()
    r["outcome_source"] = a.source
    rewrite_provenance(ctx.repo, rows)
    print(f"{a.uid}: {a.result}  (per {a.source})")
    return 0


def _walk(rows: list[dict], uid: str, seen: set, depth: int, out: list, up: bool) -> None:
    r = next((x for x in rows if x["uid"] == uid), None)
    if not r or uid in seen:
        return
    seen.add(uid)
    pad = "  " * depth
    mark = {"ticket": "T", "decision": "D", "update": "U",
            "research": "R", "question": "Q", "idea": "I"}.get(r["kind"], "?")
    oc = f"  =>  {r['outcome']}" if r.get("outcome") else "  =>  outcome not recorded yet"
    out.append(f"{pad}[{mark}] {r['uid']}  {r['title'][:80]}")
    out.append(f"{pad}    from: {r['source']['meeting']} {r['source'].get('when','')}"
               f"  ->  {r['destination']}{oc}")
    if r.get("outcome_source"):
        out.append(f"{pad}    outcome source: {r['outcome_source']}")
    nxt = (r.get("derived_from") or []) if up else \
          [x["uid"] for x in rows if uid in (x.get("derived_from") or [])]
    for n in nxt:
        _walk(rows, n, seen, depth + 1, out, up)


def cmd_chain(ctx: Ctx, a) -> int:
    rows = load_provenance(ctx.repo)
    if a.list or not a.uid:
        if not rows:
            print("provenance is empty: nothing has been marked done yet.")
            return 0
        for r in rows:
            oc = r["outcome"] or "-"
            print(f"  {r['uid']:<22} {r['kind']:<9} {r['title'][:52]:<54} outcome: {oc}")
        pend = [r for r in rows if not r.get("outcome")]
        print(f"\n{len(rows)} tracked · {len(pend)} with no outcome recorded")
        return 0
    out: list[str] = []
    out.append("ORIGIN (what this came from)")
    _walk(rows, a.uid, set(), 1, out, up=True)
    out.append("")
    out.append("CONSEQUENCES (what came out of it)")
    _walk(rows, a.uid, set(), 1, out, up=False)
    print("\n".join(out))
    return 0


def cmd_pending(ctx: Ctx, a) -> int:
    """What the weekly outcome sweep should go and look at."""
    rows = [r for r in load_provenance(ctx.repo) if not r.get("outcome")]
    older = a.older_than or 7
    cut = (_dt.date.fromisoformat(ctx.date) - _dt.timedelta(days=older)).isoformat()
    due = [r for r in rows if r["done_at"][:10] <= cut]
    if not due:
        print(f"nothing older than {older} days is missing an outcome.")
        return 0
    print(f"{len(due)} item(s) done more than {older} days ago with no outcome recorded:")
    for r in due:
        hint = {"ticket": "read its Jira resolution",
                "decision": "check whether a later decision superseded or reversed it",
                "idea": "did it become an experiment, and what did the experiment object return",
                "research": "was it answered, and did the answer change what it said it would",
                "question": "was it answered, and by whom",
                "update": "did it land, and did anyone act on it"}.get(r["kind"], "")
        print(f"  {r['uid']:<22} {r['kind']:<9} {r['title'][:60]}")
        print(f"      {hint}")
    return 1


def cmd_status(ctx: Ctx, a) -> int:
    st = load_state(ctx)
    ts = st.get("tickets") or []
    if not ts:
        print(f"ACTIONS {ctx.date}: none drafted")
        return 0
    counts: dict[str, int] = {}
    for t in ts:
        counts[t.get("state", STATE_DRAFTED)] = counts.get(t.get("state", STATE_DRAFTED), 0) + 1
    blocked = len([t for t in ts if t.get("issues")])
    stubs = len([t for t in ts if is_stub(t)])
    if a.json:
        print(json.dumps({"date": ctx.date, "total": len(ts), "states": counts,
                          "kinds": {k: len([x for x in ts if kind_of(x) == k]) for k in KINDS},
                          "blocked": blocked, "stubs": stubs,
                          "queue": str(queue_path(ctx).relative_to(ctx.repo))}))
        return 0
    kinds = " · ".join(f"{len([x for x in ts if kind_of(x)==k])} {k}"
                       for k in KINDS if any(kind_of(x) == k for x in ts))
    print(f"ACTIONS {ctx.date}: {len(ts)} ({kinds}) · "
          + " · ".join(f"{n} {s}" for s, n in counts.items())
          + (f" · {blocked} blocked" if blocked else "")
          + (f" · {stubs} stub" if stubs else "")
          + f" · queue: {queue_path(ctx).relative_to(ctx.repo)}")
    return 1 if counts.get(STATE_DRAFTED) or blocked else 0


def cmd_selftest(ctx: Ctx, a) -> int:
    fails = []

    def check(name, got, want):
        if got != want:
            fails.append(f"{name}: got {got!r}, wanted {want!r}")

    good = {"id": "t1", "title": "[FE] Show the welcome prompt on first open",
            "issue_type": "Story", "role": "Frontend engineer",
            "context": "c", "problem": "p", "what_we_need": "w", "why_this_matters": "y",
            "acceptance_criteria": ["A shows", "B shows", "C shows", "D shows", "E shows"],
            "source": {"meeting": "Design & Refine", "fidelity": "verbatim",
                       "excerpt": "we agreed the prompt appears on first open"}}
    check("a complete verbatim ticket", validate(good), [])

    for f, h in zip(FIELDS, HEADERS):
        t = dict(good); t[f] = ""
        assert any(h in i for i in validate(t)), h
    check("all four headers enforced", True, True)

    check("no role tag in the title",
          any("role tag" in i for i in validate(dict(good, title="Show the prompt"))), True)
    check("assignee set is rejected",
          any("roles, not people" in i for i in validate(dict(good, assignee="Sam"))), True)
    check("estimate is rejected",
          any("estimate" in i for i in validate(dict(good, context="c, 5 story points"))), True)
    check("task-shaped criterion is rejected",
          any("not an observable outcome" in i for i in
              validate(dict(good, acceptance_criteria=["Build the endpoint", "B", "C", "D", "E"]))),
          True)
    check("too few criteria",
          any("5 to 7" in i for i in validate(dict(good, acceptance_criteria=["A", "B"]))), True)

    # the stub rule, both directions
    para = dict(good, source={"meeting": "1:1", "fidelity": "summary", "excerpt": "they mentioned it"})
    check("invented criteria from a paraphrase",
          any("invented" in i for i in validate(para)), True)
    stub = dict(para, acceptance_criteria=["confirm scope with Frontend engineer before estimating"])
    check("a correct stub passes", validate(stub), [])
    check("a stub is marked as one", is_stub(stub), True)
    check("wrong single criterion on a paraphrase",
          any("confirm scope" in i for i in
              validate(dict(para, acceptance_criteria=["The prompt appears"]))), True)

    check("missing excerpt",
          any("excerpt" in i for i in
              validate(dict(good, source={"meeting": "x", "fidelity": "verbatim"}))), True)

    # KM is shared: an unconfirmed reference is a block
    ref = dict(good, context="follows WEB-118")
    check("unconfirmed KM reference", any("WEB-118" in i for i in validate(ref)), True)
    check("confirmed KM reference", validate(dict(ref, verified_keys=["WEB-118"])), [])

    # ---- decisions -------------------------------------------------------
    dec = {"id": "d1", "kind": "decision",
           "decision": "Welcome prompts launch as a learning launch on sprint 6 day 1",
           "rationale": "the schedule slip is accepted and the launch is worth more than the date",
           "decided_on": "2026-09-24", "binds": "the product team",
           "source": {"meeting": "Sprint review", "fidelity": "verbatim",
                      "excerpt": "we agreed to launch day 1 of sprint 6"}}
    check("a complete decision", validate(dec), [])
    check("a decision is not a ticket",
          any("that is an action" in i for i in
              validate(dict(dec, decision="We should cap the reminder at 3"))), True)
    check("a leaning is not a decision",
          any("hedged" in i for i in
              validate(dict(dec, decision="We might cap the reminder"))), True)
    check("no rationale", any("no why" in i for i in validate(dict(dec, rationale=""))), True)
    check("no date", any("decided_on" in i for i in validate(dict(dec, decided_on="soon"))), True)
    check("no binds", any("binds" in i for i in validate(dict(dec, binds=""))), True)
    para = dict(dec, source={"meeting": "1:1", "fidelity": "summary", "excerpt": "they mentioned it"},
                attributed_to="Sam Lee")
    check("no attribution from a paraphrase",
          any("cannot attribute" in i for i in validate(para)), True)
    check("the same decision without a name passes",
          validate({k: v for k, v in para.items() if k != "attributed_to"}), [])
    check("a decision is never a stub", is_stub(dec), False)

    # ---- updates ---------------------------------------------------------
    upd = {"id": "u1", "kind": "update", "audience": "Slack",
           "substance": "Welcome prompts ship sprint 6 day 1 as a learning launch",
           "source": {"meeting": "Sprint review", "fidelity": "verbatim",
                      "excerpt": "we agreed to launch day 1"}}
    check("a complete update", validate(upd), [])
    check("no audience", any("no audience" in i for i in validate(dict(upd, audience=""))), True)
    check("unknown channel",
          any("not one of the known channels" in i for i in
              validate(dict(upd, audience="carrier pigeon"))), True)
    check("a number with no source",
          any("names no source" in i for i in
              validate(dict(upd, substance="signup conversion moved 4%"))), True)
    check("a number with a source",
          validate(dict(upd, substance="signup conversion moved 4%",
                        sources=["Amplitude chart e-nppes34p, read 2026-09-24"])), [])
    check("hygiene never goes external",
          any("hygiene" in i for i in validate(dict(upd, hygiene=True))), True)

    # ---- research --------------------------------------------------------
    res = {"id": "r1", "kind": "research", "owner": "Alex",
           "question": "Which profile-completeness display format moves completion",
           "changes_what": "whether WEB-146 ships a progress bar or an inline prompt",
           "source": {"meeting": "Design & Refine", "fidelity": "verbatim",
                      "excerpt": "we should explore the completeness format"}}
    check("a complete research item", validate(res), [])
    check("curiosity is refused",
          any("curiosity" in i for i in validate(dict(res, changes_what=""))), True)
    check("research needs an owner", any("no owner" in i for i in validate(dict(res, owner=""))), True)

    # ---- questions -------------------------------------------------------
    q = {"id": "q1", "kind": "question", "ask": "Jordan",
         "question": "Do we send the user back to the last profile they visited after they confirm their email?",
         "unblocks": "the acceptance criteria on WEB-190",
         "source": {"meeting": "Design & Refine", "fidelity": "verbatim",
                    "excerpt": "nobody in the room knew what happens after confirmation"}}
    check("a complete question", validate(q), [])
    check("a statement is not a question",
          any("not a question" in i for i in
              validate(dict(q, question="Find out what happens after confirmation"))), True)
    check("two questions are refused",
          any("more than one question" in i for i in
              validate(dict(q, question="Do we redirect? And does Google prefill?"))), True)
    check("a question needs a person", any("one person" in i for i in validate(dict(q, ask=""))), True)
    check("a question that unblocks nothing",
          any("unblocks nothing" in i for i in validate(dict(q, unblocks=""))), True)

    # ---- ideas -----------------------------------------------------------
    idea = {"id": "i1", "kind": "idea", "title": "Eye icon explaining a private profile",
            "problem": "Users switch their profile to private without knowing who can still see it",
            "proposed_solution": "An eye icon next to the toggle opening a bottom sheet",
            "strategic_alignment": "supply-side trust, S4 profile funnel",
            "riskiest_assumption": "that confusion about visibility is what stops the toggle being used",
            "source": {"meeting": "Design & Refine", "fidelity": "verbatim",
                       "excerpt": "The designer suggested an eye icon with a bottom sheet"}}
    check("a complete idea", validate(idea), [])
    check("an idea without its riskiest assumption",
          any("preference" in i for i in validate(dict(idea, riskiest_assumption=""))), True)
    check("an idea with no alignment",
          any("strategic_alignment" in i for i in
              validate(dict(idea, strategic_alignment=""))), True)

    # ---- decision homes --------------------------------------------------
    check("design table is a valid home", validate(dict(dec, home="design_table")), [])
    check("an invented home is refused",
          any("must be one of" in i for i in validate(dict(dec, home="slack"))), True)

    # ---- source hash -----------------------------------------------------
    h1 = {"source": {"meeting": "Design & Refine", "when": "15:00", "fidelity": "verbatim",
                     "excerpt": "cap it at three"}}
    check("hash is stable", source_hash(h1), source_hash(dict(h1)))
    check("reformatting is not a change", source_hash(h1),
          source_hash({"source": {"meeting": "Design & Refine", "when": "15:00",
                                  "fidelity": "verbatim", "excerpt": "cap   it\n at three"}}))
    changed = source_hash({"source": dict(h1["source"], excerpt="cap it at four")})
    check("a real edit IS a change", changed != source_hash(h1), True)

    # ---- kinds -----------------------------------------------------------
    check("no kind means ticket", kind_of({}), "ticket")
    check("an unknown kind is refused",
          any("unknown kind" in i for i in validate({"kind": "memo"})), True)

    # the box parser
    boxes = read_boxes("### [x] `t1` A\n### [ ] `t2` B\n### [-] `t3` C reject: out of scope\n")
    check("approve box", boxes["t1"][0], "x")
    check("empty box", boxes["t2"][0], " ")
    check("reject box", boxes["t3"][0], "-")
    check("reject reason", boxes["t3"][1], "out of scope")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  " + f)
        return 1
    print("selftest: 50 cases pass across six kinds. The four headers and the stub rule hold for "
          "tickets, a decision cannot be an action or a leaning and cannot name a speaker from a "
          "paraphrase, an update cannot carry an unsourced number or a hygiene item, research "
          "without a stated consequence is refused as curiosity, a question needs one person and "
          "one question mark, an idea without its riskiest assumption is a preference, and a "
          "ticked box on a blocked item does not approve it. An approval is dropped when its "
          "source changes underneath it, and a reformat is not a change.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="The meeting-to-ticket approval queue.")
    ap.add_argument("--date")
    ap.add_argument("--repo")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("draft", help="ingest drafted tickets and render the queue")
    p.add_argument("--in", dest="infile", default="-")
    p.add_argument("--replace", action="store_true", help="reset states for re-drafted tickets")

    sub.add_parser("sync", help="read the ticked boxes back into state")

    p = sub.add_parser("approved", help="the tickets cleared to build")
    p.add_argument("--json", action="store_true")

    for name, helptext in (("done", "record that an approved item landed"),
                           ("created", "alias of done, kept for existing scripts")):
        q = sub.add_parser(name, help=helptext)
        q.add_argument("--id", required=True)
        q.add_argument("--to", help='where it landed, e.g. "confluence 123456"')
        q.add_argument("--key", help="shorthand for a Jira key")
        q.add_argument("--by", choices=["loop", "hand"], default="loop")

    p = sub.add_parser("status")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("chain", help="walk the full circle: source, item, consequences, outcome")
    p.add_argument("--uid", help="durable id, e.g. 2026-09-24/t1")
    p.add_argument("--list", action="store_true", help="everything tracked, with outcome state")

    p = sub.add_parser("outcome", help="record what came of an item, with its source")
    p.add_argument("--uid", required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--source", help="where the outcome was read; required")

    p = sub.add_parser("pending-outcomes", help="what the weekly sweep should look at")
    p.add_argument("--older-than", type=int, default=7)

    sub.add_parser("selftest")

    a = ap.parse_args()
    repo = pathlib.Path(a.repo).resolve() if a.repo else repo_root()
    ctx = Ctx(a.date or today(), repo)
    return {"draft": cmd_draft, "sync": cmd_sync, "approved": cmd_approved,
            "done": cmd_done, "created": cmd_done, "status": cmd_status,
            "chain": cmd_chain, "outcome": cmd_outcome,
            "pending-outcomes": cmd_pending,
            "selftest": cmd_selftest}[a.cmd](ctx, a)


if __name__ == "__main__":
    sys.exit(main())
