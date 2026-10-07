#!/usr/bin/env python3
"""
trust.py: the morning loop's trust layer.

Why this exists
---------------
Four properties decide how hard you have to read a draft, and all four were
either missing or claimable-without-being-true:

  QW1 provable grading      Was this actually checked, or does it just say so?
  QW2 correction propagation If the loop learned something mid-run, did the
                             drafts learn it too?
  QW3 legible provenance     Which parts do I need to read closely?
  QW4 an outbound record     What went out under my name, and was it verified?

QW1, QW2 and QW3 live here. QW4 lives in shipped.py, which reads the stamps
this script writes.

The load-bearing idea: a verdict is COMPUTED from recorded agent ids, never
asserted by the agent that wrote the draft. READY is unreachable unless the
stamp names verifier ids that exist, differ from the drafter, and differ from
each other. On 2026-08-26 a full two-verifier grid rendered from a session that
had no subagents at all. That is impossible here, because the ids are the grid.

Data it owns (per run day):

  {review_dir}/.trust/{job}.json      one stamp per drafted job
  {review_dir}/.trust/corrections.json  the session corrections list

Commands
--------
  trust.py stamp   --date D [--in f|-]     ingest a stamp, compute the verdict,
                                           inject the provenance header
  trust.py correct add --date D ...        record a correction; HOLD every draft
                                           in the session that has not applied it
  trust.py correct apply|dismiss|list ...  work a correction through
  trust.py header  --date D [--job J]      re-render the provenance headers
  trust.py packet  --date D                build the review packet (one .md with
                                           every draft, its verdict and its ship action)
  trust.py status  --date D                one line for the brief
  trust.py preflight --routed a,b ...      refuse to draft external work with no verifiers
  trust.py claims record --in f            record the brief's claims, print the
                                           confidence census and each claim's marker
  trust.py claims census|tags              recompute them from what was recorded
  trust.py selftest                        prove the verdict rules, no I/O

Exit codes: 0 fine · 1 something is not shippable · 2 usage/setup error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import re
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HEADER_START = "<!-- TRUST-HEADER:START -->"
HEADER_END = "<!-- TRUST-HEADER:END -->"

# Verdicts, most alarming first. The order IS the precedence.
HOLD = "HOLD"
UNVERIFIED = "UNVERIFIED"
SELF_ASSESSED = "SELF-ASSESSED"
PARTIAL = "PARTIALLY VERIFIED"
NEEDS_EDIT = "NEEDS EDIT"
READY = "READY"

VERDICT_MARK = {
    HOLD: "⛔",
    UNVERIFIED: "⚠️",
    SELF_ASSESSED: "⚠️",
    PARTIAL: "⚠️",
    NEEDS_EDIT: "⚠️",
    READY: "✅",
}

DEFAULT_REVIEW_DIR = "morning/drafts/{DATE}"
DEFAULT_PACKET = "morning/drafts/{DATE}/review-packet.md"
DEFAULT_PLAN = "morning/briefs/{DATE}.md"


def die(msg: str, code: int = 2) -> "NoReturn":  # type: ignore[valid-type]
    print(f"trust.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


WORKSPACE_MARKERS = ("morning/state",)


def repo_root(start: pathlib.Path | None = None) -> pathlib.Path:
    # The workspace you run from wins. The scripts are LINKED into a
    # workspace (scripts/setup.py), so resolving __file__ lands in the
    # package clone and its .git, and every stamp and packet would be written into
    # the package instead of the workspace. Found by a fresh-install test.
    if start is None:
        cwd = pathlib.Path.cwd()
        for cand in [cwd, *cwd.parents]:
            if any((cand / m).is_dir() for m in WORKSPACE_MARKERS):
                return cand
    p = (start or pathlib.Path(__file__)).resolve()
    for cand in [p] + list(p.parents):
        if (cand / ".git").exists():
            return cand
    return pathlib.Path.cwd()


def today(tz_hint: str | None = None) -> str:
    return _dt.date.today().isoformat()


def now_hm() -> str:
    return _dt.datetime.now().strftime("%H:%M")


def now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

class Ctx:
    def __init__(self, date: str, repo: pathlib.Path,
                 review_dir: str | None = None,
                 packet: str | None = None,
                 plan: str | None = None):
        self.date = date
        self.repo = repo
        self.review_dir = repo / (review_dir or DEFAULT_REVIEW_DIR).replace("{DATE}", date)
        self.trust_dir = self.review_dir / ".trust"
        self.packet_path = repo / (packet or DEFAULT_PACKET).replace("{DATE}", date)
        self.plan_path = repo / (plan or DEFAULT_PLAN).replace("{DATE}", date)

    @property
    def corrections_path(self) -> pathlib.Path:
        return self.trust_dir / "corrections.json"

    def stamp_path(self, job: str) -> pathlib.Path:
        return self.trust_dir / f"{slug(job)}.json"

    def stamps(self) -> list[dict]:
        if not self.trust_dir.is_dir():
            return []
        out = []
        for f in sorted(self.trust_dir.glob("*.json")):
            if f.name == "corrections.json":
                continue
            try:
                d = json.loads(f.read_text())
            except json.JSONDecodeError as e:
                die(f"corrupt stamp {f}: {e}")
            # A stamp is identified by its SHAPE, not by its filename. Other
            # scripts write their own state into this same directory (tickets.py
            # writes tickets.json), so a deny-list by name silently breaks the
            # moment one more writer is added. It did: on 2026-09-01, the first
            # run to hold both a ticket queue and a correction, rerender() died
            # with KeyError: 'job' on tickets.json and took the entire verdict
            # layer down mid-run, which means nothing could be stamped and
            # nothing could be graded. Anything without a job key is not a stamp.
            if isinstance(d, dict) and d.get("job"):
                out.append(d)
        return out


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", (s or "").strip().lower()).strip("-") or "unnamed"


def load_corrections(ctx: Ctx) -> list[dict]:
    if not ctx.corrections_path.exists():
        return []
    return json.loads(ctx.corrections_path.read_text())


def save_corrections(ctx: Ctx, items: list[dict]) -> None:
    ctx.trust_dir.mkdir(parents=True, exist_ok=True)
    ctx.corrections_path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# QW1: the verdict is computed, never claimed
# ---------------------------------------------------------------------------

def independent_verifiers(stamp: dict) -> tuple[list[str], list[str]]:
    """Return (accepted verifier ids, rejected-with-reason strings).

    A verifier counts only if it has a non-blank id, that id is not the
    drafter's, and it has not already been counted. Everything else is a
    self-assessment wearing a verifier's hat.
    """
    drafter = str((stamp.get("drafter") or {}).get("agent_id") or "").strip()
    accepted: list[str] = []
    rejected: list[str] = []
    for i, v in enumerate(stamp.get("verifiers") or [], start=1):
        vid = str((v or {}).get("agent_id") or "").strip()
        if not vid:
            rejected.append(f"verifier {i}: no agent id recorded")
            continue
        if drafter and vid == drafter:
            rejected.append(f"verifier {i}: same agent as the drafter ({vid})")
            continue
        if vid in accepted:
            rejected.append(f"verifier {i}: duplicate of an earlier verifier ({vid})")
            continue
        accepted.append(vid)
    return accepted, rejected


def required_verifiers(stamp: dict) -> int:
    """stricter_for_external: anything that would leave the workspace needs two."""
    ext = stamp.get("external_action")
    if isinstance(ext, list):
        ext = [e for e in ext if e and str(e).lower() != "none"]
        return 2 if ext else 1
    if ext and str(ext).lower() not in ("none", "local", "null", "false"):
        return 2
    return 1


def resolved_checks(stamp: dict) -> list[dict]:
    """Flatten every verifier's per-check results, applying the judge's rulings.

    A check appears once. Where verifiers disagree the judge's ruling wins; with
    no ruling, disagreement resolves to fail, because the grader contract
    defaults to fail when uncertain.
    """
    by_id: dict[str, dict] = {}
    for vi, v in enumerate(stamp.get("verifiers") or [], start=1):
        for c in (v or {}).get("checks") or []:
            cid = str(c.get("id") or "").strip()
            if not cid:
                continue
            res = str(c.get("result") or "fail").lower()
            rec = by_id.setdefault(cid, {
                "id": cid,
                "severity": str(c.get("severity") or "normal").lower(),
                "results": [],
            })
            if c.get("severity"):
                rec["severity"] = str(c["severity"]).lower()
            rec["results"].append({"verifier": vi, "result": res,
                                   "reason": c.get("reason") or ""})
    rulings = {str(r.get("id") or "").strip(): str(r.get("result") or "").lower()
               for r in (stamp.get("judge") or {}).get("rulings") or []}
    out = []
    for cid, rec in by_id.items():
        results = [r["result"] for r in rec["results"]]
        applicable = [r for r in results if r != "n/a"]
        if not applicable:
            final = "n/a"
        elif cid in rulings and len(set(applicable)) > 1:
            final = rulings[cid]
        elif all(r == "pass" for r in applicable):
            final = "pass"
        else:
            final = "fail"
        who = ", ".join(f"verifier {r['verifier']}" for r in rec["results"]
                        if r["result"] == "fail") or None
        reason = next((r["reason"] for r in rec["results"] if r["result"] == "fail"), "")
        out.append({"id": cid, "result": final, "severity": rec["severity"],
                    "failed_by": who, "reason": reason,
                    "adjudicated": cid in rulings and len(set(applicable)) > 1})
    return sorted(out, key=lambda c: c["id"])


def open_corrections_for(stamp: dict, corrections: list[dict]) -> list[dict]:
    """Session corrections this draft has neither applied nor dismissed."""
    job = stamp.get("job")
    seen = set(stamp.get("corrections_seen") or [])
    out = []
    for c in corrections:
        if c.get("id") in seen:
            continue
        state = (c.get("drafts") or {}).get(job)
        if state in ("applied", "dismissed"):
            continue
        # A correction raised before this draft even started cannot have been
        # missed by it only if the drafter was told; we do not assume that.
        out.append(c)
    return out


def grade(stamp: dict, corrections: list[dict]) -> dict:
    """The whole of QW1 in one function. Everything else renders this."""
    accepted, rejected = independent_verifiers(stamp)
    need = required_verifiers(stamp)
    checks = resolved_checks(stamp)
    failed = [c for c in checks if c["result"] == "fail"]
    blocked = [c for c in failed if c["severity"] == "block"]
    passed = [c for c in checks if c["result"] == "pass"]
    applicable = [c for c in checks if c["result"] != "n/a"]
    open_corr = open_corrections_for(stamp, corrections)

    if open_corr:
        verdict, why = HOLD, (f"{len(open_corr)} session correction(s) not applied to this draft: "
                              + "; ".join(c.get("id", "?") for c in open_corr))
    elif not (stamp.get("verifiers") or []):
        verdict, why = UNVERIFIED, "no verifier ran"
    elif not accepted:
        verdict, why = SELF_ASSESSED, "; ".join(rejected) or "no independent verifier"
    elif len(accepted) < need:
        verdict, why = PARTIAL, (f"{len(accepted)} independent verifier(s) of {need} required "
                                 f"for external_action={stamp.get('external_action')}")
    elif blocked:
        verdict, why = NEEDS_EDIT, ("block-severity check failed: "
                                    + ", ".join(c["id"] for c in blocked))
    elif failed:
        verdict, why = NEEDS_EDIT, "failed: " + ", ".join(c["id"] for c in failed)
    else:
        verdict, why = READY, f"{len(passed)} of {len(applicable)} applicable checks passed"

    return {
        "verdict": verdict,
        "why": why,
        "independent_verifiers": accepted,
        "rejected_verifiers": rejected,
        "required_verifiers": need,
        "checks": checks,
        "failed": failed,
        "passed": passed,
        "applicable": applicable,
        "open_corrections": open_corr,
        "shippable": verdict == READY,
    }


# ---------------------------------------------------------------------------
# QW3: the provenance header
# ---------------------------------------------------------------------------

def _fmt_ext(ext) -> str:
    if isinstance(ext, list):
        ext = [e for e in ext if e and str(e).lower() != "none"]
        return " + ".join(str(e) for e in ext) if ext else "local only"
    if not ext or str(ext).lower() in ("none", "local", "null", "false"):
        return "local only"
    return str(ext)


def render_header(stamp: dict, g: dict) -> str:
    v = g["verdict"]
    lines: list[str] = []

    lines.append(f"VERDICT     {v} · {g['why']}")

    drafter = str((stamp.get("drafter") or {}).get("agent_id") or "not recorded")
    verifiers = ", ".join(g["independent_verifiers"]) or "none"
    judge = str((stamp.get("judge") or {}).get("agent_id") or "")
    grading = (f"GRADING     {len(g['independent_verifiers'])} independent verifier(s) of "
               f"{g['required_verifiers']} required · drafter {drafter} · verifiers {verifiers}")
    if judge:
        grading += f" · judge {judge}"
    lines.append(grading)
    for r in g["rejected_verifiers"]:
        lines.append(f"            not counted: {r}")

    if g["applicable"]:
        lines.append(f"VERIFIED    {len(g['passed'])} of {len(g['applicable'])} applicable checks passed")

    req = stamp.get("requeried") or []
    if req:
        lines.append("REQUERIED   " + " · ".join(
            f"{r.get('source','?')} ({r.get('at','?')})" for r in req))

    carried = stamp.get("carried") or []
    if carried:
        lines.append("CARRIED     " + " · ".join(
            f"{c.get('claim','?')} (brief #{c.get('from_brief','?')}, age {c.get('age_days','?')}d)"
            for c in carried))

    exp = stamp.get("expires") or []
    if exp:
        lines.append("EXPIRES     " + " · ".join(
            f"{e.get('what','?')} ({e.get('why','?')})" for e in exp))

    if g["failed"]:
        lines.append("FAILED      " + " · ".join(
            f"{c['id']}" + (f" ({c['failed_by']})" if c["failed_by"] else "")
            + (f": {c['reason']}" if c["reason"] else "")
            for c in g["failed"]))

    corr = stamp.get("corrections_applied") or []
    if corr:
        lines.append("CORRECTIONS " + " · ".join(
            f"{c.get('id','?')} {c.get('state','applied')} {c.get('at','')}".strip()
            for c in corr))
    for c in g["open_corrections"]:
        lines.append(f"CORRECTION  OPEN {c.get('id','?')}: was \"{c.get('was','')}\" "
                     f"→ now \"{c.get('now','')}\" · patch or dismiss before shipping")

    unav = stamp.get("unavailable") or []
    if unav:
        lines.append("UNAVAILABLE " + " · ".join(str(u) for u in unav))

    ext = _fmt_ext(stamp.get("external_action"))
    if ext == "local only":
        lines.append("SHIPS TO    local only · this draft has no external destination")
    else:
        lines.append(f"SHIPS TO    {ext}"
                     + ("" if g["shippable"] else " · NOT cleared to ship")
                     + " · nothing has been sent")
    lines.append(f"STAMPED     {stamp.get('stamped_at', now_iso())}"
                 + (f" · skill {stamp['skill']}" if stamp.get("skill") else "")
                 + f" · trust.py grade, not the drafter's word")

    mark = VERDICT_MARK.get(v, "⚠️")
    banner = (f"> {mark} **{v}** · {_fmt_ext(stamp.get('external_action'))} · "
              f"nothing here has been sent to anyone.")
    body = "\n".join(lines)
    return f"{HEADER_START}\n{banner}\n\n```text\n{body}\n```\n{HEADER_END}"


def reading_guide(stamp: dict, g: dict) -> tuple[str, str]:
    """(read closely, safe to skim) — computed, not asserted.

    The trust header already carries everything needed to decide reading depth:
    which checks failed, what was carried, what expires, what could not be
    reached. Nobody assembles it into an instruction, so the reader does that
    work themselves on every draft. This does it once.
    """
    close, skim = [], []

    failed = g["failed"]
    if failed:
        close.append(f"the {len(failed)} failed check"
                     + ("s" if len(failed) > 1 else "")
                     + ": " + ", ".join(c["id"] for c in failed[:4]))
    for c in stamp.get("expires") or []:
        close.append(f"{c.get('what','?')}, which expires ({c.get('why','')})")
    carried = stamp.get("carried") or []
    if carried:
        close.append(f"{len(carried)} claim(s) carried from an earlier brief, not re-read today")
    for c in g["open_corrections"]:
        close.append(f"correction {c.get('id','?')}, unapplied")
    unav = stamp.get("unavailable") or []
    if unav:
        close.append(f"anything resting on {', '.join(str(u) for u in unav[:3])}, "
                     f"which could not be reached this run")

    passed = len(g["passed"])
    if passed:
        skim.append(f"{passed} check(s) passed")
    req = stamp.get("requeried") or []
    if req:
        skim.append(f"{len(req)} source(s) re-queried this morning "
                    f"({', '.join(r.get('source','?') for r in req[:2])})")
    if not close:
        skim.append("nothing in it is carried, expiring or unreachable")

    return (" · ".join(close) or "nothing flagged",
            " · ".join(skim) or "nothing verified, so read all of it")


def inject_header(path: pathlib.Path, header: str) -> None:
    """Replace the header block in place, or insert it under the H1."""
    if not path.exists():
        return
    text = path.read_text()
    if HEADER_START in text and HEADER_END in text:
        pre = text.split(HEADER_START)[0]
        post = text.split(HEADER_END, 1)[1]
        path.write_text(pre + header + post)
        return
    lines = text.splitlines(keepends=True)
    at = 0
    for i, ln in enumerate(lines[:10]):
        if ln.startswith("# "):
            at = i + 1
            break
    while at < len(lines) and lines[at].strip() == "":
        at += 1
    out = lines[:at] + [header + "\n\n"] + lines[at:]
    path.write_text("".join(out))


def strip_header(text: str) -> str:
    if HEADER_START in text and HEADER_END in text:
        return text.split(HEADER_START)[0] + text.split(HEADER_END, 1)[1]
    return text


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def read_json_input(arg: str | None) -> dict:
    if arg in (None, "-"):
        raw = sys.stdin.read()
    else:
        p = pathlib.Path(arg)
        if not p.exists():
            die(f"no such stamp input: {arg}")
        raw = p.read_text()
    if not raw.strip():
        die("empty stamp input")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"stamp input is not valid JSON: {e}")


def cmd_stamp(ctx: Ctx, a) -> int:
    incoming = read_json_input(a.infile)
    job = a.job or incoming.get("job")
    if not job:
        die("a stamp needs a job id (--job or \"job\" in the JSON)")
    incoming["job"] = job
    incoming["date"] = ctx.date

    path = ctx.stamp_path(job)
    stamp: dict = {}
    if path.exists() and not a.replace:
        stamp = json.loads(path.read_text())
    # merge: lists in the incoming stamp replace, they do not append, so a
    # re-stamp after a revision reflects the latest grading and nothing older.
    stamp.update(incoming)

    if not stamp.get("artifact"):
        guess = ctx.review_dir / f"{slug(job)}.md"
        stamp["artifact"] = str(guess.relative_to(ctx.repo)) if guess.exists() else ""
    stamp["stamped_at"] = now_iso()

    corrections = load_corrections(ctx)
    g = grade(stamp, corrections)
    stamp["verdict"] = g["verdict"]
    stamp["verdict_why"] = g["why"]

    ctx.trust_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stamp, indent=2, ensure_ascii=False) + "\n")

    if stamp.get("artifact") and not a.no_header:
        inject_header(ctx.repo / stamp["artifact"], render_header(stamp, g))

    print(f"{VERDICT_MARK.get(g['verdict'],'?')} {job}: {g['verdict']} · {g['why']}")
    if a.json:
        print(json.dumps({"job": job, **{k: g[k] for k in ("verdict", "why", "shippable")}}))
    return 0 if g["verdict"] == READY else 1


def cmd_correct(ctx: Ctx, a) -> int:
    items = load_corrections(ctx)

    if a.corr_cmd == "list":
        if not items:
            print(f"no corrections recorded for {ctx.date}")
            return 0
        for c in items:
            states = c.get("drafts") or {}
            print(f"{c['id']}  {c.get('at','')}  was: {c.get('was','')}")
            print(f"      now: {c.get('now','')}  source: {c.get('source','')}")
            for job, st in states.items():
                print(f"      {job}: {st}")
        return 0

    if a.corr_cmd == "add":
        if not (a.was and a.now):
            die("a correction needs --was and --now")
        cid = a.id or f"c{len(items) + 1}"
        if any(c["id"] == cid for c in items):
            die(f"correction {cid} already exists")
        corr = {"id": cid, "at": now_iso(), "was": a.was, "now": a.now,
                "source": a.source or "", "drafts": {}}

        # propagate: every draft already written this session is suspect until
        # it says otherwise. Drafts whose text literally carries the wrong claim
        # are named, because those are the ones that must be patched.
        hits: list[str] = []
        needle = re.sub(r"\s+", " ", a.was.strip().lower())
        for stamp in ctx.stamps():
            job = stamp.get("job")
            art = stamp.get("artifact")
            body = ""
            if art and (ctx.repo / art).exists():
                body = re.sub(r"\s+", " ", (ctx.repo / art).read_text().lower())
            state = "carries-the-claim" if needle and needle in body else "open"
            corr["drafts"][job] = state
            if state == "carries-the-claim":
                hits.append(job)
        items.append(corr)
        save_corrections(ctx, items)
        rerender(ctx)

        print(f"correction {cid} recorded. {len(corr['drafts'])} draft(s) put on HOLD.")
        if hits:
            print("literally carries the wrong claim: " + ", ".join(hits))
        print("clear each with: trust.py correct apply --id " + cid + " --job <job>   "
              "(after patching)  ·  or  correct dismiss --id " + cid +
              " --job <job> --reason \"...\"")
        return 1

    if a.corr_cmd in ("apply", "dismiss"):
        if not (a.id and a.job):
            die(f"correct {a.corr_cmd} needs --id and --job")
        corr = next((c for c in items if c["id"] == a.id), None)
        if not corr:
            die(f"no correction {a.id} for {ctx.date}")
        if a.corr_cmd == "dismiss" and not a.reason:
            die("dismissing a correction needs --reason: say why it does not apply")
        corr.setdefault("drafts", {})[a.job] = a.corr_cmd + "ed" if a.corr_cmd == "dismiss" else "applied"
        if a.reason:
            corr.setdefault("reasons", {})[a.job] = a.reason
        save_corrections(ctx, items)

        sp = ctx.stamp_path(a.job)
        if sp.exists():
            stamp = json.loads(sp.read_text())
            stamp.setdefault("corrections_applied", [])
            stamp["corrections_applied"] = [c for c in stamp["corrections_applied"]
                                            if c.get("id") != a.id]
            stamp["corrections_applied"].append(
                {"id": a.id, "state": "applied" if a.corr_cmd == "apply" else "dismissed",
                 "at": now_hm(), "reason": a.reason or ""})
            sp.write_text(json.dumps(stamp, indent=2, ensure_ascii=False) + "\n")
        rerender(ctx)
        print(f"correction {a.id} {corr['drafts'][a.job]} for {a.job}")
        return 0

    die("unknown correct subcommand")


def rerender(ctx: Ctx) -> None:
    """Recompute every verdict and re-inject every header. Cheap, idempotent."""
    corrections = load_corrections(ctx)
    for stamp in ctx.stamps():
        g = grade(stamp, corrections)
        stamp["verdict"] = g["verdict"]
        stamp["verdict_why"] = g["why"]
        ctx.stamp_path(stamp["job"]).write_text(
            json.dumps(stamp, indent=2, ensure_ascii=False) + "\n")
        if stamp.get("artifact"):
            inject_header(ctx.repo / stamp["artifact"], render_header(stamp, g))


def cmd_header(ctx: Ctx, a) -> int:
    stamps = ctx.stamps()
    if a.job:
        stamps = [s for s in stamps if s.get("job") == a.job]
    if not stamps:
        print(f"no stamps for {ctx.date}"
              + (f" matching job {a.job}" if a.job else "")
              + f" (looked in {ctx.trust_dir})")
        return 1
    rerender(ctx)
    for s in stamps:
        print(f"{VERDICT_MARK.get(s.get('verdict'),'?')} {s['job']}: {s.get('verdict')}")
    return 0


# ---------------------------------------------------------------------------
# The review packet: one file that holds every draft, its verdict and its
# ship action, so the review is a single pass rather than a directory crawl.
# ---------------------------------------------------------------------------

def demote(md: str, by: int = 2, cap: int = 6) -> str:
    out = []
    fence = False
    for ln in md.splitlines():
        if ln.lstrip().startswith("```"):
            fence = not fence
            out.append(ln)
            continue
        if not fence:
            m = re.match(r"^(#{1,6})(\s)", ln)
            if m:
                lvl = min(len(m.group(1)) + by, cap)
                ln = "#" * lvl + ln[len(m.group(1)):]
        out.append(ln)
    return "\n".join(out)


def plan_section(plan_text: str, markers: tuple[str, ...]) -> str:
    """Pull one section out of the morning plan by any of its heading markers."""
    lines = plan_text.splitlines()
    start = None
    level = 2
    for i, ln in enumerate(lines):
        if ln.startswith("#") and any(m.lower() in ln.lower() for m in markers):
            start = i + 1
            level = len(ln) - len(ln.lstrip("#"))
            break
    if start is None:
        return ""
    out = []
    for ln in lines[start:]:
        if ln.startswith("#"):
            lvl = len(ln) - len(ln.lstrip("#"))
            if lvl <= level:
                break
        out.append(ln)
    return "\n".join(out).strip()


def unstamped_drafts(ctx: Ctx) -> list[pathlib.Path]:
    if not ctx.review_dir.is_dir():
        return []
    stamped = {str((ctx.repo / s["artifact"]).resolve())
               for s in ctx.stamps() if s.get("artifact")}
    return [f for f in sorted(ctx.review_dir.glob("*.md"))
            if str(f.resolve()) not in stamped
            and f.name not in ("tickets-from-meetings.md", "meeting-actions.md")]
            # the action queue has its own gate and its own approval file


def cmd_packet(ctx: Ctx, a) -> int:
    stamps = ctx.stamps()
    loose = unstamped_drafts(ctx)
    if not stamps and not loose:
        die(f"nothing to pack: no drafts in {ctx.review_dir}", 1)

    corrections = load_corrections(ctx)
    graded = [(s, grade(s, corrections)) for s in stamps]
    graded.sort(key=lambda sg: (
        [READY, NEEDS_EDIT, PARTIAL, SELF_ASSESSED, UNVERIFIED, HOLD].index(sg[1]["verdict"]),
        sg[0].get("job", "")))

    counts: dict[str, int] = {}
    for _, g in graded:
        counts[g["verdict"]] = counts.get(g["verdict"], 0) + 1
    tally = " · ".join(f"{n} {v}" for v, n in counts.items()) or "none"

    L: list[str] = []
    L.append(f"# Review packet {ctx.date}")
    L.append("")
    L.append(f"**{len(graded)} draft(s) stamped: {tally}."
             + (f" {len(loose)} draft file(s) with no stamp." if loose else "")
             + "  Nothing here has been sent to anyone.**")
    L.append("")
    L.append("Every verdict below is computed by `trust.py` from the recorded agent ids, "
             "not asserted by the agent that wrote the draft. `READY` is unreachable without "
             "verifier ids that exist and differ from the drafter.")
    L.append("")

    if corrections:
        openc = [c for c in corrections
                 if any(st not in ("applied", "dismissed")
                        for st in (c.get("drafts") or {}).values())]
        L.append("## Corrections raised this session")
        L.append("")
        for c in corrections:
            states = c.get("drafts") or {}
            flag = "OPEN" if any(st not in ("applied", "dismissed") for st in states.values()) else "closed"
            L.append(f"- **{c['id']} ({flag})** was: *{c.get('was','')}* → now: *{c.get('now','')}* "
                     f"· source: {c.get('source','not recorded')}")
            for job, st in states.items():
                L.append(f"    - {job}: `{st}`")
        if openc:
            L.append("")
            L.append("> An open correction holds every draft that has not applied it. "
                     "Nothing ships out of a session with an unapplied correction.")
        L.append("")

    L.append("## What is in front of you")
    L.append("")
    L.append("| # | draft | verdict | would ship to | your move |")
    L.append("|---|---|---|---|---|")
    for i, (s, g) in enumerate(graded, start=1):
        move = {READY: "read the header, then ship",
                NEEDS_EDIT: "fix the failed check, then ship",
                PARTIAL: "second verifier missing, read it in full",
                SELF_ASSESSED: "ungraded, read it in full",
                UNVERIFIED: "ungraded, read it in full",
                HOLD: "apply the correction first"}[g["verdict"]]
        L.append(f"| {i} | [{s.get('job')}](#{i}-{slug(s.get('job',''))}) "
                 f"| {VERDICT_MARK[g['verdict']]} {g['verdict']} "
                 f"| {_fmt_ext(s.get('external_action'))} | {move} |")
    for f in loose:
        L.append(f"| · | `{f.name}` | ⚠️ NO STAMP | unknown | "
                 f"read it in full, and find out why it was never graded |")
    L.append("")

    tq = next((ctx.review_dir / n for n in ("meeting-actions.md",
                                           "tickets-from-meetings.md")
               if (ctx.review_dir / n).exists()), ctx.review_dir / "meeting-actions.md")
    if tq.exists():
        state = ctx.trust_dir / "tickets.json"
        line = ""
        if state.exists():
            try:
                ts = json.loads(state.read_text()).get("tickets") or []
                by: dict[str, int] = {}
                for x in ts:
                    by[x.get("state", "drafted")] = by.get(x.get("state", "drafted"), 0) + 1
                kinds: dict[str, int] = {}
                for x in ts:
                    k = (x.get("kind") or "ticket")
                    kinds[k] = kinds.get(k, 0) + 1
                blocked = len([x for x in ts if x.get("issues")])
                line = (f"{len(ts)} action(s) ("
                        + ", ".join(f"{n} {k}" for k, n in kinds.items()) + "): "
                        + " · ".join(f"{n} {s}" for s, n in by.items())
                        + (f" · {blocked} blocked by a format rule" if blocked else ""))
            except (json.JSONDecodeError, OSError):
                line = "state unreadable"
        L.append("## Actions from meetings")
        L.append("")
        L.append(f"{line}  Approve by ticking the boxes in "
                 f"[`{tq.relative_to(ctx.repo)}`]({tq.name}), then run "
                 f"`tickets.py --date {ctx.date} sync`. Nothing is created in Jira until you tick "
                 f"a box and confirm again at the ship gate.")
        L.append("")

    if ctx.plan_path.exists():
        plan = ctx.plan_path.read_text()
        for title, markers in (
            ("Decisions waiting on you", ("NEEDS YOUR DECISION", "🟡", "❓", "DECISION")),
            ("Your turn", ("YOUR TURN", "🧠", "HUMAN")),
            ("Findings this run", ("FINDINGS",)),
        ):
            body = plan_section(plan, markers)
            if body:
                L.append(f"## {title}")
                L.append("")
                L.append(body)
                L.append("")

    L.append("---")
    L.append("")
    L.append("# The drafts")
    L.append("")

    for i, (s, g) in enumerate(graded, start=1):
        job = s.get("job", "unnamed")
        L.append(f"## {i}. {job}")
        L.append("")
        art = s.get("artifact") or ""
        L.append(f"**Source:** `{art or 'no file recorded'}`"
                 + (f" · **skill:** `{s['skill']}`" if s.get("skill") else ""))
        L.append("")
        L.append("```text")
        L.append(render_header(s, g).split("```text\n", 1)[-1].rsplit("```", 1)[0].rstrip())
        L.append("```")
        L.append("")
        dest = s.get("destination") or _fmt_ext(s.get("external_action"))
        if g["verdict"] == READY:
            L.append(f"**Ship action:** publish to {dest}. After you send it, record it:")
        else:
            L.append(f"**Ship action:** blocked ({g['why']}). Would go to {dest}. "
                     f"If you send it anyway, record it honestly:")
        L.append("")
        L.append("```bash")
        L.append(f"python3 morning/engine/shipped.py add \\")
        L.append(f"  --job {job} --to \"{dest}\" --by hand")
        L.append("```")
        L.append("")
        close, skim = reading_guide(s, g)
        L.append("**Decide from this.**")
        L.append("")
        L.append(f"- **What it is:** {s.get('job')}"
                 + (f", via `{s['skill']}`" if s.get("skill") else ""))
        L.append(f"- **If you ship it:** {dest}")
        L.append(f"- **Verdict:** {g['verdict']}, {g['why']}")
        L.append(f"- **Read closely:** {close}")
        L.append(f"- **Safe to skim:** {skim}")
        L.append("")
        L.append("<details><summary>Full draft</summary>")
        L.append("")

        if art and (ctx.repo / art).exists():
            body = strip_header((ctx.repo / art).read_text()).strip()
            blines = body.splitlines()
            if a.max_lines and len(blines) > a.max_lines:
                body = "\n".join(blines[:a.max_lines])
                body += (f"\n\n*[{len(blines) - a.max_lines} more lines. "
                         f"Full draft: `{art}`]*")
            L.append(demote(body))
        else:
            L.append("*No draft file found for this stamp.*")
        L.append("")
        L.append("</details>")
        L.append("")
        L.append("---")
        L.append("")

    for f in loose:
        L.append(f"## Unstamped: {f.name}")
        L.append("")
        L.append(f"**No trust stamp exists for this file**, so nothing is known about how it "
                 f"was graded. Source: `{f.relative_to(ctx.repo)}`")
        L.append("")
        body = strip_header(f.read_text()).strip().splitlines()
        if a.max_lines and len(body) > a.max_lines:
            body = body[:a.max_lines] + ["", f"*[truncated. Full draft: `{f.relative_to(ctx.repo)}`]*"]
        L.append(demote("\n".join(body)))
        L.append("")
        L.append("---")
        L.append("")

    ctx.packet_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.packet_path.write_text("\n".join(L).rstrip() + "\n")
    print(f"review packet: {ctx.packet_path.relative_to(ctx.repo)} "
          f"({len(graded)} stamped, {len(loose)} unstamped)")
    return 0


def cmd_status(ctx: Ctx, a) -> int:
    corrections = load_corrections(ctx)
    graded = [(s, grade(s, corrections)) for s in ctx.stamps()]
    loose = unstamped_drafts(ctx)
    counts: dict[str, int] = {}
    for _, g in graded:
        counts[g["verdict"]] = counts.get(g["verdict"], 0) + 1
    openc = [c for c in corrections
             if any(st not in ("applied", "dismissed")
                    for st in (c.get("drafts") or {}).values())]
    if a.json:
        print(json.dumps({
            "date": ctx.date,
            "stamped": len(graded),
            "unstamped": len(loose),
            "verdicts": counts,
            "open_corrections": [c["id"] for c in openc],
            "packet": str(ctx.packet_path.relative_to(ctx.repo)),
            "packet_exists": ctx.packet_path.exists(),
        }))
        return 0
    parts = [f"{len(graded)} stamped"] + [f"{n} {v}" for v, n in counts.items()]
    if loose:
        parts.append(f"{len(loose)} UNSTAMPED")
    if openc:
        parts.append(f"{len(openc)} open correction(s)")
    print(f"TRUST {ctx.date}: " + " · ".join(parts)
          + f" · packet: {ctx.packet_path.relative_to(ctx.repo)}"
          + ("" if ctx.packet_path.exists() else " (not built yet)"))
    return 1 if (loose or openc) else 0


# ---------------------------------------------------------------------------
# preflight: refuse to draft external work the run cannot grade
# ---------------------------------------------------------------------------

CONFIG_CANDIDATES = (
    "{env}",
    "{repo}/morning/config.yml",
)


def find_config(repo: pathlib.Path, explicit: str | None) -> pathlib.Path | None:
    if explicit:
        p = pathlib.Path(explicit)
        return p if p.exists() else None
    user = (os.environ.get("USER") or "").split()[0].lower()
    for tmpl in CONFIG_CANDIDATES:
        s = tmpl.format(env=os.environ.get("MORNING_CONFIG", ""), repo=repo, user=user)
        if not s or "{" in s:
            continue
        p = pathlib.Path(s)
        if p.exists():
            return p
    return None


def routing_external_actions(cfg_text: str) -> dict[str, str]:
    """id -> external_action, for the routing block only. Deliberately small."""
    out: dict[str, str] = {}
    in_routing = False
    cur = None
    for raw in cfg_text.splitlines():
        if re.match(r"^\w[\w_]*:", raw):
            in_routing = raw.startswith("routing:")
            if not in_routing:
                cur = None
            continue
        if not in_routing:
            continue
        line = raw.split("#", 1)[0].rstrip()
        m = re.match(r"^\s*-\s*id:\s*(\S+)", line)
        if m:
            cur = m.group(1).strip().strip('"\'')
            out.setdefault(cur, "none")
            continue
        m = re.match(r"^\s*external_action:\s*(.+)$", line)
        if m and cur:
            out[cur] = m.group(1).strip().strip('"\'')
    return out


def cmd_preflight(ctx: Ctx, a) -> int:
    cfg = find_config(ctx.repo, a.config)
    if not cfg:
        die("no config found; pass --config")
    actions = routing_external_actions(cfg.read_text())
    routed = [r.strip() for r in (a.routed or "").split(",") if r.strip()]
    unknown = [r for r in routed if r not in actions]
    external = [r for r in routed
                if str(actions.get(r, "none")).lower() not in ("none", "local", "[]")]
    subagents = (a.subagents or "yes").lower() in ("yes", "true", "1", "y")

    print(f"PREFLIGHT trust: config {cfg.name} · routed {len(routed)} "
          f"· external {len(external)} · subagents {'available' if subagents else 'UNAVAILABLE'}")
    if unknown:
        print("  not in routing: " + ", ".join(unknown))
    if external and not subagents:
        print("  ⛔ STOP. These jobs would leave the workspace and cannot be independently "
              "verified this run:")
        for r in external:
            print(f"     {r} -> {actions[r]}")
        print("  Per quality.on_independence_unavailable they must be labelled UNVERIFIED and "
              "carry no rubric table. trust.py cannot render READY for them, and it will not.")
        return 1
    if external:
        print("  external jobs need two independent verifiers each: " + ", ".join(external))
    return 0


# ---------------------------------------------------------------------------
# claims: the brief's confidence census and inline markers
# ---------------------------------------------------------------------------
#
# The provenance header answers "which parts do I need to read closely" per
# DRAFT. The brief carries roughly 40 claims and got one verdict, and on the
# first run the gate was pointed at 3 of about 40. Uniform presentation
# invites uniform trust. So every claim in the brief carries one of four
# markers, and the brief opens with the count of each.
#
# The marker is COMPUTED from what was recorded, the same rule as a draft
# verdict: `verified` needs a verifier agent id that is not the probe's own,
# plus the source it re-queried and when. Nothing here takes the loop's word.
#
#   verified  [V hh:mm]  re-queried live by an independent verifier this run
#   reported  [R]        one source, read this run, not re-queried
#   inferred  [I]        derived from other claims, no direct source
#   carried   [C]        from an earlier brief or an earlier day's read, not
#                        re-checked today
#   unsourced [?]        none of the above. Should be zero; shown when it is not
#
# Stored as {review_dir}/.trust/claims.json. It has no `job` key, so stamps()
# never mistakes it for a draft stamp.

MARKERS = ("verified", "reported", "inferred", "carried", "unsourced")


def _hm(stamp: str) -> str:
    m = re.search(r"(\d{1,2}:\d{2})", str(stamp or ""))
    return m.group(1) if m else ""


def _day(stamp: str) -> str:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", str(stamp or ""))
    return m.group(1) if m else ""


def claim_marker(c: dict, run_date: str) -> tuple[str, str, str]:
    """(marker, inline tag, why). Precedence: verified, carried, reported,
    inferred, unsourced. A carried claim that was re-queried today IS verified;
    re-checking is exactly what un-carries it."""
    probe = str(c.get("probe_agent") or "").strip()
    for v in c.get("verifiers") or []:
        vid = str((v or {}).get("agent_id") or "").strip()
        if not vid or (probe and vid == probe):
            continue
        if str(v.get("result") or "pass").lower() == "fail":
            continue
        req, at = str(v.get("requeried") or "").strip(), str(v.get("at") or "").strip()
        if req and at and _day(at) in ("", run_date):
            return "verified", f"[V {_hm(at)}]".replace(" ]", "]"), f"{vid} re-queried {req}"
    read_day = _day(c.get("read_at"))
    if c.get("carried_from") or (read_day and read_day < run_date):
        src = c.get("carried_from") or f"read {read_day}"
        return "carried", "[C]", f"from {src}, not re-checked today"
    if str(c.get("source") or "").strip() and str(c.get("read_at") or "").strip():
        return "reported", "[R]", f"one source: {c['source']}"
    if c.get("derived_from"):
        return "inferred", "[I]", "derived from " + ", ".join(map(str, c["derived_from"]))
    return "unsourced", "[?]", "no source, no derivation, no verifier recorded"


def correction_summary(corrections: list[dict]) -> tuple[int, int]:
    """(registered, cleared). Cleared means every draft it touched applied or
    dismissed it; a correction that touched no draft is cleared by definition."""
    cleared = sum(1 for c in corrections
                  if all(st in ("applied", "dismissed")
                         for st in (c.get("drafts") or {}).values()))
    return len(corrections), cleared


def census(claims: list[dict], corrections: list[dict], run_date: str) -> dict:
    counts = {m: 0 for m in MARKERS}
    killed = failed = 0
    tags: dict[str, str] = {}
    for c in claims:
        if c.get("killed"):
            killed += 1
            continue
        m, tag, _ = claim_marker(c, run_date)
        counts[m] += 1
        if c.get("id"):
            tags[str(c["id"])] = tag
        if any(str((v or {}).get("result") or "").lower() == "fail"
               for v in c.get("verifiers") or []):
            failed += 1
    reg, cleared = correction_summary(corrections)
    total = sum(counts.values())
    line = (f"{total} claims: {counts['verified']} verified live, {counts['reported']} reported, "
            f"{counts['inferred']} inferred, {counts['carried']} carried.")
    if counts["unsourced"]:
        line += f" {counts['unsourced']} UNSOURCED."
    if failed:
        line += f" {failed} still in the brief after a verifier failed it."
    if killed:
        line += f" {killed} killed by the gate."
    if reg == 0:
        line += " 0 corrections registered."
    elif cleared == reg:
        line += (f" {reg} correction registered, cleared." if reg == 1 else
                 f" {reg} corrections registered, {'both' if reg == 2 else 'all'} cleared.")
    else:
        noun = "correction" if reg == 1 else "corrections"
        line += f" {reg} {noun} registered, {reg - cleared} still open."
    return {"total": total, "counts": counts, "killed": killed, "failed_in_brief": failed,
            "corrections": reg, "corrections_cleared": cleared, "tags": tags, "line": line}


def claims_path(ctx: Ctx) -> pathlib.Path:
    return ctx.trust_dir / "claims.json"


def load_claims(ctx: Ctx) -> list[dict]:
    p = claims_path(ctx)
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    return d.get("claims", []) if isinstance(d, dict) else list(d)


def cmd_claims(ctx: Ctx, a) -> int:
    if a.claims_cmd == "record":
        data = read_json_input(a.infile)
        items = data.get("claims") if isinstance(data, dict) else data
        if not isinstance(items, list):
            die("claims record wants a JSON list of claims, or {\"claims\": [...]}")
        missing = [i for i, c in enumerate(items, 1) if not (c.get("id") and c.get("text"))]
        if missing:
            die(f"every claim needs an id and its text; missing on item(s) {missing}")
        ctx.trust_dir.mkdir(parents=True, exist_ok=True)
        claims_path(ctx).write_text(json.dumps(
            {"date": ctx.date, "recorded_at": now_iso(), "claims": items},
            indent=2, ensure_ascii=False) + "\n")
    claims = load_claims(ctx)
    cs = census(claims, load_corrections(ctx), ctx.date)
    if a.json:
        print(json.dumps(cs, ensure_ascii=False))
        return 0
    print("CENSUS " + cs["line"])
    if a.claims_cmd in ("record", "tags"):
        for c in claims:
            if c.get("killed"):
                continue
            m, tag, why = claim_marker(c, ctx.date)
            print(f"  {tag:<9} {c['id']}: {why}")
    return 1 if (cs["counts"]["unsourced"] or cs["failed_in_brief"]) else 0


# ---------------------------------------------------------------------------
# selftest: the verdict rules, proved, with no filesystem
# ---------------------------------------------------------------------------

def cmd_selftest(ctx: Ctx, a) -> int:
    fails: list[str] = []

    def check(name, got, want):
        if got != want:
            fails.append(f"{name}: got {got!r}, wanted {want!r}")

    ok = [{"id": "grounded", "result": "pass"}, {"id": "terse", "result": "pass"}]

    # 1. the 2026-08-26 failure: drafter grades itself, grid rendered READY
    s = {"job": "weekly", "external_action": "confluence",
         "drafter": {"agent_id": "a1"},
         "verifiers": [{"agent_id": "a1", "checks": ok}, {"agent_id": "a1", "checks": ok}]}
    check("self-graded external", grade(s, [])["verdict"], SELF_ASSESSED)

    # 2. verifier with no id recorded is not a verifier
    s2 = {"job": "weekly", "external_action": "none", "drafter": {"agent_id": "a1"},
          "verifiers": [{"checks": ok}]}
    check("id-less verifier", grade(s2, [])["verdict"], SELF_ASSESSED)

    # 3. one real verifier clears a local draft
    s3 = {"job": "notes", "external_action": "none", "drafter": {"agent_id": "a1"},
          "verifiers": [{"agent_id": "a2", "checks": ok}]}
    check("local, one verifier", grade(s3, [])["verdict"], READY)

    # 4. the same stamp bound for Confluence needs two
    s4 = dict(s3, external_action="confluence")
    check("external, one verifier", grade(s4, [])["verdict"], PARTIAL)

    # 5. two distinct verifiers clear it
    s5 = dict(s4, verifiers=[{"agent_id": "a2", "checks": ok},
                             {"agent_id": "a3", "checks": ok}])
    check("external, two verifiers", grade(s5, [])["verdict"], READY)

    # 6. duplicate id is one verifier, not two
    s6 = dict(s4, verifiers=[{"agent_id": "a2", "checks": ok},
                             {"agent_id": "a2", "checks": ok}])
    check("duplicate verifier id", grade(s6, [])["verdict"], PARTIAL)

    # 7. no verifiers at all
    s7 = {"job": "x", "external_action": "none", "drafter": {"agent_id": "a1"}}
    check("no verifier", grade(s7, [])["verdict"], UNVERIFIED)

    # 8. disagreement with no judge resolves to fail
    s8 = {"job": "x", "external_action": "none", "drafter": {"agent_id": "a1"},
          "verifiers": [{"agent_id": "a2", "checks": [{"id": "terse", "result": "pass"}]},
                        {"agent_id": "a3", "checks": [{"id": "terse", "result": "fail"}]}]}
    check("unjudged disagreement", grade(s8, [])["verdict"], NEEDS_EDIT)

    # 9. the judge settles it
    s9 = dict(s8, judge={"agent_id": "a4", "rulings": [{"id": "terse", "result": "pass"}]})
    check("judged disagreement", grade(s9, [])["verdict"], READY)

    # 10. a block-severity fail both verifiers agree on is never READY
    s10 = {"job": "x", "external_action": "none", "drafter": {"agent_id": "a1"},
           "verifiers": [{"agent_id": "a2", "checks": [{"id": "grounded", "result": "fail",
                                                        "severity": "block"}]},
                         {"agent_id": "a3", "checks": [{"id": "grounded", "result": "fail",
                                                        "severity": "block"}]}],
           "judge": {"agent_id": "a4", "rulings": [{"id": "grounded", "result": "pass"}]}}
    check("agreed block fail", grade(s10, [])["verdict"], NEEDS_EDIT)

    # 11. QW2: an unapplied session correction holds an otherwise-perfect draft
    corr = [{"id": "c1", "was": "no object exists", "now": "10448399 exists", "drafts": {}}]
    check("open correction", grade(s5, corr)["verdict"], HOLD)

    # 12. and clears once the draft applies it
    s12 = dict(s5, corrections_seen=["c1"])
    check("applied correction", grade(s12, corr)["verdict"], READY)

    # 13. dismissal is per draft, and only for the draft that dismissed it
    corr2 = [{"id": "c1", "was": "w", "now": "n", "drafts": {"weekly": "dismissed"}}]
    check("dismissed for this draft", grade(dict(s5, job="weekly"), corr2)["verdict"], READY)
    check("still open for another", grade(dict(s5, job="other"), corr2)["verdict"], HOLD)

    # 14. n/a checks do not block
    s14 = {"job": "x", "external_action": "none", "drafter": {"agent_id": "a1"},
           "verifiers": [{"agent_id": "a2", "checks": [{"id": "a", "result": "n/a"},
                                                       {"id": "b", "result": "pass"}]}]}
    check("n/a checks", grade(s14, [])["verdict"], READY)

    # 15. a list external_action of only "none" is local
    check("external_action [none]", required_verifiers({"external_action": ["none"]}), 1)
    check("external_action list", required_verifiers({"external_action": ["confluence",
                                                                          "mattermost"]}), 2)


    # 16. D6: a claim is verified only by an independent verifier that re-queried
    D = "2026-09-29"
    v_ok = {"id": "k1", "text": "t", "probe_agent": "p1", "source": "JQL", "read_at": "08:01",
            "verifiers": [{"agent_id": "v1", "requeried": "Jira REST", "at": "2026-09-29T08:14"}]}
    check("independent requery is verified", claim_marker(v_ok, D)[0], "verified")
    check("verified tag carries the time", claim_marker(v_ok, D)[1], "[V 08:14]")
    self_v = dict(v_ok, verifiers=[{"agent_id": "p1", "requeried": "Jira", "at": "08:14"}])
    check("probe checking itself is only reported", claim_marker(self_v, D)[0], "reported")
    no_req = dict(v_ok, verifiers=[{"agent_id": "v1", "at": "08:14"}])
    check("a verifier that did not requery does not verify", claim_marker(no_req, D)[0],
          "reported")

    # 17. carried, inferred, unsourced, and a stale read counts as carried
    check("carried from an earlier brief",
          claim_marker({"id": "k", "text": "t", "carried_from": "brief #4"}, D)[0], "carried")
    check("yesterday's read is carried",
          claim_marker({"id": "k", "text": "t", "source": "x", "read_at": "2026-09-28T09:00"},
                       D)[0], "carried")
    check("re-queried today un-carries it",
          claim_marker(dict(v_ok, carried_from="brief #4"), D)[0], "verified")
    check("derived is inferred",
          claim_marker({"id": "k", "text": "t", "derived_from": ["k1", "k2"]}, D)[0], "inferred")
    check("nothing recorded is unsourced", claim_marker({"id": "k", "text": "t"}, D)[0],
          "unsourced")

    # 18. D7: the census line, killed claims excluded, corrections counted
    cl = [v_ok, {"id": "k2", "text": "t", "source": "s", "read_at": "08:00"},
          {"id": "k3", "text": "t", "derived_from": ["k1"]},
          {"id": "k4", "text": "t", "carried_from": "brief #4"},
          {"id": "k5", "text": "t", "killed": True}]
    cr = [{"id": "c1", "drafts": {"weekly": "applied"}}, {"id": "c2", "drafts": {}}]
    cs = census(cl, cr, D)
    check("census line", cs["line"], "4 claims: 1 verified live, 1 reported, 1 inferred, "
          "1 carried. 1 killed by the gate. 2 corrections registered, both cleared.")
    cs2 = census(cl[:1], [{"id": "c1", "drafts": {"weekly": "open"}}], D)
    check("open correction shows", cs2["line"].endswith("1 correction registered, 1 still open."),
          True)

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  " + f)
        return 1
    print("selftest: 18 cases pass. READY is unreachable without distinct verifier ids, "
          "an open correction holds every draft in the session, and a brief claim is "
          "verified only by an independent re-query.")
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="The morning loop's trust layer.")
    ap.add_argument("--date", help="run date (YYYY-MM-DD), default today")
    ap.add_argument("--repo", help="repo root, default: the git root above this script")
    ap.add_argument("--review-dir", help="override paths.review_dir template")
    ap.add_argument("--packet", help="override the review packet path template")
    ap.add_argument("--plan", help="override paths.plan_file template")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("stamp", help="record how a draft was graded and stamp it")
    p.add_argument("--job")
    p.add_argument("--in", dest="infile", default="-", help="stamp JSON file, or - for stdin")
    p.add_argument("--replace", action="store_true", help="discard any existing stamp")
    p.add_argument("--no-header", action="store_true")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("correct", help="session corrections (QW2)")
    p.add_argument("corr_cmd", choices=["add", "apply", "dismiss", "list"])
    p.add_argument("--id")
    p.add_argument("--job")
    p.add_argument("--was", help="the claim as drafted, verbatim")
    p.add_argument("--now", help="what is actually true")
    p.add_argument("--source", help="where the correct value was read")
    p.add_argument("--reason", help="why a dismissal is legitimate")

    p = sub.add_parser("header", help="re-render the provenance headers")
    p.add_argument("--job")

    p = sub.add_parser("packet", help="build the review packet")
    p.add_argument("--max-lines", type=int, default=400,
                   help="per-draft inline cap, 0 for no cap")

    p = sub.add_parser("status", help="one line for the brief")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("preflight", help="can this run grade what it is about to draft?")
    p.add_argument("--config")
    p.add_argument("--routed", help="comma-separated routing rule ids firing this run")
    p.add_argument("--subagents", choices=["yes", "no"], default="yes")

    p = sub.add_parser("claims", help="the brief's confidence census and markers (D6, D7)")
    p.add_argument("claims_cmd", choices=["record", "census", "tags"])
    p.add_argument("--in", dest="infile", default="-", help="claims JSON file, or - for stdin")
    p.add_argument("--json", action="store_true")

    sub.add_parser("selftest", help="prove the verdict rules")

    a = ap.parse_args()
    repo = pathlib.Path(a.repo).resolve() if a.repo else repo_root()
    ctx = Ctx(a.date or today(), repo, a.review_dir, a.packet, a.plan)

    return {
        "stamp": cmd_stamp, "correct": cmd_correct, "header": cmd_header,
        "packet": cmd_packet, "status": cmd_status, "preflight": cmd_preflight,
        "selftest": cmd_selftest, "claims": cmd_claims,
    }[a.cmd](ctx, a)


if __name__ == "__main__":
    sys.exit(main())
