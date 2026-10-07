#!/usr/bin/env python3
"""
ontime.py: was the brief there when the day started, without anyone asking?

Why this exists
---------------
Delivery success said 20 of 27 weekdays, 74%, and it was measuring the wrong
thing. Lag against the scheduled fire said 1 of 21. Same artefacts, two
numbers, and only the second one redirects the work. "It dispatched" and "it
ran" look identical in every artefact an adopter reads, so this script reads
the lag instead of the exit code.

Per weekday it computes:

  fire           the scheduled fire (schedule.time on that date)
  delivered_at   first delivery, from the receipt (first_sent_at, else sent_at)
  lag_min        delivered_at minus fire, in minutes
  by_runner      the delivery landed inside an unattended runner block in
                 launchd.log, so nobody had to open a session to get it
  class          unattended  delivered by the runner within the grace window
                 late        delivered, but after the grace window, or only
                             because a person ran it by hand
                 missed      a run was attempted (receipt or runner block) and
                             nothing was delivered that day
                 no_record   no receipt and no runner block. Reported, never
                             counted in the denominator, never guessed at

Only the receipts and launchd.log are read. Nothing here estimates a value for
a day with no evidence. When sent_at is all a receipt has, a later re-delivery
may have overwritten the first one, so that lag is an UPPER bound and the row
says so (`lag_basis: sent_at`). notify.py keeps `first_sent_at` from
2026-09-28 on, which removes that caveat for new days.

"No interactive session open" is approximated by "the delivery timestamp falls
inside a runner block". A person running run-prep.sh by hand is
indistinguishable from launchd here, which is a known limit.

Commands
--------
  ontime.py record  [--date D] [--no-write]   classify D, write `on_time` into
                                              D's receipt, upsert one run-log
                                              line, print the fragment
  ontime.py report  [--asof D] [--window N] [--json]   the rolling rate
  ontime.py history [--json]                  every weekday with evidence
  ontime.py selftest                          the classifier, proved, no I/O

Exit codes: 0 fine · 2 usage/setup error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import statistics
import sys

# Windows consoles default to a legacy code page and crash on ✓ or →; print UTF-8 instead.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = pathlib.Path(__file__).resolve().parent
WORKSPACE_MARKERS = ("morning/state",)
WEEKDAY_NUM = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

DEFAULTS = {
    "fire_at": "07:50",
    "weekdays": [0, 1, 2, 3, 4],
    "grace_minutes": 15,
    "window_weekdays": 10,
    "substrate": "unknown",
}

# A delivery a little after the runner's own "finished" line still belongs to
# that run: the safety net re-delivers and then prints the finished line.
RUNNER_TAIL_SECS = 120

START_RE = re.compile(r"^===== (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) starting /morning --prep")
END_RE = re.compile(r"^===== (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) finished \(exit (-?\d+)\)")
SLEPT_RE = re.compile(r"^watchdog: machine slept for about (\d+) min")
NONET_RE = re.compile(r"^===== (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) no network at fire time")


# --------------------------------------------------------------------------- paths
def find_root(explicit: str | None) -> pathlib.Path:
    if explicit:
        return pathlib.Path(explicit).expanduser().resolve()
    for start in (pathlib.Path.cwd(), HERE):
        for p in [start, *start.parents]:
            if any((p / m).is_dir() for m in WORKSPACE_MARKERS):
                return p
    return HERE.parent


def artefacts_dir(root: pathlib.Path) -> pathlib.Path:
    if any((root / m).is_dir() for m in WORKSPACE_MARKERS):
        return root / "morning" / "state"
    return root / "briefs"


CONFIG_CANDIDATES = (
    "{env}",
    "{repo}/morning/config.yml",
)


def find_config(root: pathlib.Path, explicit: str | None) -> pathlib.Path | None:
    if explicit:
        p = pathlib.Path(explicit).expanduser()
        return p if p.is_file() else None
    user = (os.environ.get("USER") or os.environ.get("USERNAME") or "").lower()   # Windows sets USERNAME
    for tpl in CONFIG_CANDIDATES:
        raw = tpl.format(env=os.environ.get("MORNING_CONFIG", ""), repo=root, user=user)
        if raw and pathlib.Path(raw).is_file():
            return pathlib.Path(raw)
    return None


def parse_yaml_min(text: str) -> dict:
    """Nested `key: value` mappings only, which is all this script reads.

    No PyYAML dependency on purpose: the runner calls this from a launchd
    environment where only the system python is guaranteed.
    """
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or raw.lstrip().startswith("-"):
            continue
        m = re.match(r"^(\s*)([A-Za-z_][\w-]*):\s*(.*)$", raw)
        if not m:
            continue
        ind, key, val = len(m.group(1)), m.group(2), m.group(3)
        val = re.sub(r"\s+#.*$", "", val).strip()
        while stack and stack[-1][0] >= ind:
            stack.pop()
        parent = stack[-1][1]
        if val == "":
            child: dict = {}
            parent[key] = child
            stack.append((ind, child))
        else:
            parent[key] = val.strip("\"'")
    return root


def load_settings(root: pathlib.Path, cfg_path: pathlib.Path | None) -> dict:
    s = dict(DEFAULTS)
    if not cfg_path:
        return s
    cfg = parse_yaml_min(cfg_path.read_text())
    sched = cfg.get("schedule") if isinstance(cfg.get("schedule"), dict) else {}
    health = cfg.get("health") if isinstance(cfg.get("health"), dict) else {}
    ot = health.get("on_time") if isinstance(health.get("on_time"), dict) else {}
    t = str(ot.get("fire_at") or sched.get("time") or "")
    if re.match(r"^\d{1,2}:\d{2}$", t):
        s["fire_at"] = t
    wd = str(sched.get("weekdays") or "")
    days = [WEEKDAY_NUM[d] for d in re.findall(r"[a-z]{3}", wd.lower()) if d in WEEKDAY_NUM]
    if days:
        s["weekdays"] = days
    for k in ("grace_minutes", "window_weekdays"):
        if str(ot.get(k, "")).isdigit():
            s[k] = int(ot[k])
    sub = str(sched.get("substrate") or "")
    if sub and not sub.startswith("<"):
        s["substrate"] = sub
    paths = cfg.get("paths") if isinstance(cfg.get("paths"), dict) else {}
    if paths.get("run_log"):
        s["run_log"] = str(root / paths["run_log"])
    return s


# --------------------------------------------------------------------------- evidence
def parse_runner_blocks(log_text: str, now: dt.datetime | None = None) -> list[dict]:
    """Runner blocks from launchd.log: start, end, and what happened inside.

    An unclosed LAST block is a run still in progress (this script is called
    from inside it), so its end is `now`. An unclosed block followed by another
    start was killed without a finished line; it ends where the next begins.
    """
    blocks: list[dict] = []
    cur: dict | None = None
    nonet: list[dt.datetime] = []
    for line in log_text.splitlines():
        m = START_RE.match(line)
        if m:
            if cur is not None:
                cur["end"] = dt.datetime.fromisoformat(m.group(1))
                cur["closed"] = False
                blocks.append(cur)
            cur = {"start": dt.datetime.fromisoformat(m.group(1)), "end": None,
                   "exit": None, "slept_min": 0, "catchup": "catch-up" in line,
                   "closed": True}
            continue
        m = NONET_RE.match(line)
        if m:
            nonet.append(dt.datetime.fromisoformat(m.group(1)))
            continue
        if cur is None:
            continue
        m = SLEPT_RE.match(line)
        if m:
            cur["slept_min"] += int(m.group(1))
            continue
        m = END_RE.match(line)
        if m:
            cur["end"] = dt.datetime.fromisoformat(m.group(1))
            cur["exit"] = int(m.group(2))
            blocks.append(cur)
            cur = None
    if cur is not None:
        cur["end"] = now or dt.datetime.now()
        cur["closed"] = False
        blocks.append(cur)
    for t in nonet:
        blocks.append({"start": t, "end": t, "exit": 75, "slept_min": 0,
                       "catchup": True, "closed": True, "no_network": True})
    return blocks


def to_local_naive(stamp: str | None) -> dt.datetime | None:
    if not stamp:
        return None
    try:
        t = dt.datetime.fromisoformat(stamp)
    except ValueError:
        try:
            t = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return None
    if t.tzinfo is not None:
        t = t.astimezone().replace(tzinfo=None)
    return t


def fire_time(day: dt.date, fire_at: str) -> dt.datetime:
    h, m = (int(x) for x in fire_at.split(":"))
    return dt.datetime.combine(day, dt.time(h, m))


def classify(day: dt.date, receipt: dict | None, blocks: list[dict], s: dict) -> dict:
    """One weekday, from its receipt and the runner blocks that STARTED on it."""
    fire = fire_time(day, s["fire_at"])
    todays = [b for b in blocks if b["start"].date() == day]
    row: dict = {"date": day.isoformat(), "fire": s["fire_at"],
                 "grace_minutes": s["grace_minutes"], "runner_attempts": len(todays)}
    status = (receipt or {}).get("status")
    delivered = status in ("sent", "rendered_not_sent")
    first = (receipt or {}).get("first_sent_at")
    stamp = first or (receipt or {}).get("sent_at") or (
        (receipt or {}).get("rendered_at") if status == "rendered_not_sent" else None)
    at = to_local_naive(stamp) if delivered else None
    slept = sum(b.get("slept_min", 0) for b in todays)
    if slept:
        row["slept_min"] = slept
    if any(b.get("no_network") for b in todays):
        row["no_network_attempts"] = sum(1 for b in todays if b.get("no_network"))

    if receipt is None and not todays:
        row["class"] = "no_record"
        return row
    if not delivered or at is None:
        row["class"] = "missed"
        row["cause"] = (receipt or {}).get("stage") or (
            "no receipt written" if receipt is None else f"receipt status {status}")
        return row

    tail = dt.timedelta(seconds=RUNNER_TAIL_SECS)
    by_runner = any(b["start"] <= at <= b["end"] + tail
                    for b in blocks if not b.get("no_network"))
    lag = round((at - fire).total_seconds() / 60)
    row.update({
        "delivered_at": at.strftime("%Y-%m-%d %H:%M"),
        "lag_min": lag,
        "lag_basis": "first_sent_at" if first else "sent_at",
        "by_runner": by_runner,
        "interactive_needed": not by_runner,
    })
    row["class"] = "unattended" if (by_runner and lag <= s["grace_minutes"]) else "late"
    return row


def fragment(row: dict) -> str:
    """The one line the run log and the brief's health line carry."""
    c = row["class"]
    if c == "no_record":
        return f"{row['date']} on-time: no record (no receipt, no runner attempt)"
    if c == "missed":
        extra = ""
        if row.get("no_network_attempts"):
            extra = f" · {row['no_network_attempts']} attempt(s) found no network"
        if row.get("slept_min"):
            extra += f" · machine slept {row['slept_min']} min mid-run"
        return (f"{row['date']} on-time: missed · fire {row['fire']} · "
                f"{row['runner_attempts']} runner attempt(s) · cause: {row.get('cause')}{extra}")
    who = ("delivered by the unattended runner, no interactive session"
           if row["by_runner"] else "delivered only from an interactive session")
    bound = "" if row["lag_basis"] == "first_sent_at" else " (upper bound: sent_at may be a re-delivery)"
    slept = f" · machine slept {row['slept_min']} min mid-run" if row.get("slept_min") else ""
    return (f"{row['date']} on-time: {c} · lag {row['lag_min']} min{bound} "
            f"(fire {row['fire']}, delivered {row['delivered_at'][11:]}, grace "
            f"{row['grace_minutes']}) · {who}{slept}")


# --------------------------------------------------------------------------- I/O
class Env:
    def __init__(self, a):
        self.root = find_root(a.root)
        self.art = artefacts_dir(self.root)
        self.cfg = find_config(self.root, a.config)
        self.s = load_settings(self.root, self.cfg)
        self.receipts = pathlib.Path(a.receipts) if a.receipts else self.art / "receipts"
        self.launchd = pathlib.Path(a.launchd_log) if a.launchd_log else self.art / "runner.log"
        self.run_log = pathlib.Path(a.run_log) if a.run_log else pathlib.Path(
            self.s.get("run_log") or self.art / "run-log.md")

    def blocks(self) -> list[dict]:
        if not self.launchd.exists():
            return []
        return parse_runner_blocks(self.launchd.read_text(errors="replace"))

    def receipt(self, day: dt.date) -> dict | None:
        p = self.receipts / f"{day.isoformat()}.json"
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text())
            return d if isinstance(d, dict) else None
        except (json.JSONDecodeError, OSError):
            return None

    def first_day(self) -> dt.date | None:
        """History starts at the first receipt. Before receipts existed a runner
        block with no receipt says nothing about delivery, so scoring those days
        as missed would invent a value; they are out of range instead."""
        days = [dt.date.fromisoformat(p.stem) for p in self.receipts.glob("????-??-??.json")]
        return min(days) if days else None

    def rows(self, upto: dt.date) -> list[dict]:
        blocks = self.blocks()
        first = self.first_day()
        if not first:
            return []
        out = []
        d = first
        while d <= upto:
            if d.weekday() in self.s["weekdays"]:
                out.append(classify(d, self.receipt(d), blocks, self.s))
            d += dt.timedelta(days=1)
        return out


def summarise(rows: list[dict], window: int, substrate: str) -> dict:
    recorded = [r for r in rows if r["class"] != "no_record"]
    win = recorded[-window:]
    no_rec_in_span = 0
    if win:
        lo = win[0]["date"]
        no_rec_in_span = sum(1 for r in rows if r["class"] == "no_record" and r["date"] >= lo)
    n = {c: sum(1 for r in win if r["class"] == c) for c in ("unattended", "late", "missed")}
    lags = [r["lag_min"] for r in win if "lag_min" in r]
    inter = sum(1 for r in win if r.get("interactive_needed"))
    upper = sum(1 for r in win if r.get("lag_basis") == "sent_at")
    return {
        "substrate": substrate,
        "window_weekdays": len(win),
        "from": win[0]["date"] if win else None,
        "to": win[-1]["date"] if win else None,
        "unattended": n["unattended"], "late": n["late"], "missed": n["missed"],
        "unattended_run_rate": (round(n["unattended"] / len(win), 3) if win else None),
        "median_lag_min": (round(statistics.median(lags)) if lags else None),
        "delivered": len(lags),
        "interactive_needed": inter,
        "lag_upper_bound_rows": upper,
        "no_record_weekdays_in_span": no_rec_in_span,
    }


def report_line(sm: dict) -> str:
    if not sm["window_weekdays"]:
        return "on-time: no receipts or runner history yet, nothing to report"
    med = f"median lag {sm['median_lag_min']} min over {sm['delivered']} delivered" \
        if sm["median_lag_min"] is not None else "no deliveries to take a lag from"
    tail = []
    if sm["interactive_needed"]:
        tail.append(f"{sm['interactive_needed']} needed an interactive session")
    if sm["lag_upper_bound_rows"]:
        tail.append(f"{sm['lag_upper_bound_rows']} lag(s) are upper bounds (sent_at only)")
    if sm["no_record_weekdays_in_span"]:
        tail.append(f"{sm['no_record_weekdays_in_span']} weekday(s) with no record, not counted")
    return (f"on-time ({sm['substrate']}, {sm['from']} to {sm['to']}): unattended "
            f"{sm['unattended']} of {sm['window_weekdays']} weekdays, late {sm['late']}, "
            f"missed {sm['missed']} · {med}" + (" · " + " · ".join(tail) if tail else ""))


def upsert_run_log(path: pathlib.Path, day: str, line: str) -> None:
    """Exactly one on-time line per day. The catch-up can fire many times a
    morning, and a line per attempt would bury the one that matters."""
    prefix = f"- {day} on-time:"
    text = path.read_text() if path.exists() else ""
    lines = text.split("\n")
    new = f"- {line}"
    for i, l in enumerate(lines):
        if l.startswith(prefix):
            lines[i] = new
            path.write_text("\n".join(lines))
            return
    sep = "" if text.endswith("\n\n") or not text else ("\n" if text.endswith("\n") else "\n\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + sep + new + "\n")


# --------------------------------------------------------------------------- commands
def cmd_record(e: Env, a) -> int:
    day = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    if day.weekday() not in e.s["weekdays"]:
        print(f"{day} on-time: not a scheduled weekday, nothing recorded")
        return 0
    row = classify(day, e.receipt(day), e.blocks(), e.s)
    line = fragment(row)
    print(line)
    if a.no_write or row["class"] == "no_record":
        return 0
    p = e.receipts / f"{day.isoformat()}.json"
    if p.exists():
        try:
            rec = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            rec = None
        if isinstance(rec, dict):
            rec["on_time"] = {k: v for k, v in row.items() if k != "date"} | {
                "recorded_at": dt.datetime.now().astimezone().isoformat(timespec="seconds")}
            p.write_text(json.dumps(rec, indent=2) + "\n")
    upsert_run_log(e.run_log, day.isoformat(), line)
    return 0


def cmd_report(e: Env, a) -> int:
    asof = dt.date.fromisoformat(a.asof) if a.asof else dt.date.today()
    rows = e.rows(asof)
    sm = summarise(rows, a.window or e.s["window_weekdays"], e.s["substrate"])
    if a.json:
        print(json.dumps(sm | {"grace_minutes": e.s["grace_minutes"], "fire": e.s["fire_at"]}))
    else:
        print(report_line(sm))
    return 0


def cmd_history(e: Env, a) -> int:
    rows = e.rows(dt.date.today())
    if a.json:
        print(json.dumps(rows, indent=2))
        return 0
    for r in rows:
        print(fragment(r))
    return 0


def cmd_selftest(_e, _a) -> int:
    fails: list[str] = []

    def check(name, got, want):
        if got != want:
            fails.append(f"{name}: got {got!r}, wanted {want!r}")

    s = dict(DEFAULTS)
    log = "\n".join([
        "===== 2026-09-28 07:50:01 starting /morning --prep (catch-up: x) =====",
        "API Error: Can't reach the API server (ENOTFOUND)",
        "===== 2026-09-28 08:27:36 claude finished (exit 1) =====",
        "===== 2026-09-28 08:27:36 finished (exit 1) =====",
        "===== 2026-09-28 09:33:31 starting /morning --prep (catch-up: x) =====",
        "===== 2026-09-28 10:06:27 finished (exit 0) =====",
        "===== 2026-09-29 07:50:02 starting /morning --prep =====",
        "===== 2026-09-29 08:03:00 finished (exit 0) =====",
        "===== 2026-09-30 07:55:40 no network at fire time: x =====",
        "===== 2026-10-01 07:50:01 starting /morning --prep =====",
        "watchdog: machine slept for about 250 min (wall clock 08:01:23 to 12:11:03)",
        "===== 2026-10-01 12:40:00 finished (exit 1) =====",
    ])
    b = parse_runner_blocks(log, now=dt.datetime(2026, 10, 1, 13, 0))
    check("blocks parsed (4 runs + 1 no-network marker)", len(b), 5)

    D = dt.date
    # 1. the 2026-09-28 shape: delivered by the second runner block, 136 min late
    r = classify(D(2026, 9, 28), {"status": "sent", "sent_at": "2026-09-28T10:06:27"}, b, s)
    check("late by runner, class", r["class"], "late")
    check("late by runner, by_runner", r["by_runner"], True)
    check("late by runner, lag", r["lag_min"], 136)
    check("sent_at only is an upper bound", r["lag_basis"], "sent_at")
    # 2. on time, runner, first_sent_at preferred over a later re-delivery
    r = classify(D(2026, 9, 29), {"status": "sent", "first_sent_at": "2026-09-29T08:02:00",
                                  "sent_at": "2026-09-29T09:30:00"}, b, s)
    check("unattended", r["class"], "unattended")
    check("first_sent_at wins", r["lag_min"], 12)
    # 3. same lag, but delivered outside any runner block: a person had to run it
    r = classify(D(2026, 9, 29), {"status": "sent", "sent_at": "2026-09-29T08:05:30"},
                 [x for x in b if x["start"].date() != D(2026, 9, 29)], s)
    check("interactive delivery is never unattended", r["class"], "late")
    check("interactive flagged", r["interactive_needed"], True)
    # 4. no-network attempt, failed receipt: missed, with the named cause
    r = classify(D(2026, 9, 30), {"status": "failed", "stage": "no network at fire time"}, b, s)
    check("no network is missed", r["class"], "missed")
    check("no network cause kept", r["cause"], "no network at fire time")
    check("no network attempts counted", r.get("no_network_attempts"), 1)
    # 5. a night with no receipt and no attempt is not invented into a miss
    r = classify(D(2026, 10, 2), None, b, s)
    check("no evidence is no_record", r["class"], "no_record")
    # 6. the machine froze mid-run: missed, and the sleep is reported, not a timeout
    r = classify(D(2026, 10, 1), {"status": "failed", "stage": "The Mac slept mid-run"}, b, s)
    check("slept minutes carried", r.get("slept_min"), 250)
    # 6b. rendered_not_sent as notify.py really writes it: sent_at null, rendered_at set
    r = classify(D(2026, 9, 29), {"status": "rendered_not_sent", "sent_at": None,
                                  "rendered_at": "2026-09-29T07:58:00"}, b, s)
    check("file channel measured by rendered_at", r["class"] != "missed", True)
    # 7. rendered_not_sent (channel file) counts as delivered
    r = classify(D(2026, 9, 29), {"status": "rendered_not_sent",
                                  "sent_at": "2026-09-29T07:58:00"}, b, s)
    check("file channel counts as delivered", r["class"], "unattended")
    # 8. the summary excludes no_record from the denominator and says so
    rows = [{"date": "2026-09-28", "class": "late", "lag_min": 136, "lag_basis": "sent_at",
             "interactive_needed": False},
            {"date": "2026-09-29", "class": "unattended", "lag_min": 12,
             "lag_basis": "first_sent_at", "interactive_needed": False},
            {"date": "2026-09-30", "class": "missed"},
            {"date": "2026-10-01", "class": "no_record"}]
    sm = summarise(rows, 10, "local_launchd")
    check("denominator excludes no_record", sm["window_weekdays"], 3)
    check("unattended count", sm["unattended"], 1)
    check("median lag", sm["median_lag_min"], 74)
    check("no_record reported", sm["no_record_weekdays_in_span"], 1)
    # 9. the minimal YAML reader finds the values the runner depends on
    cfg = parse_yaml_min("schedule:\n  time: \"07:50\"   # c\n  weekdays: [mon, tue]\n"
                         "health:\n  on_time:\n    grace_minutes: 20\n")
    check("yaml nested", cfg["health"]["on_time"]["grace_minutes"], "20")
    check("yaml comment stripped", cfg["schedule"]["time"], "07:50")

    if fails:
        print("SELFTEST FAILED")
        for f in fails:
            print("  " + f)
        return 1
    print("selftest: 9 cases pass. A day with no evidence is never scored, an interactive "
          "delivery is never unattended, and a frozen run reports its sleep.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Lag against the scheduled fire.")
    ap.add_argument("--root", default=os.environ.get("MORNING_ROOT"))
    ap.add_argument("--config")
    ap.add_argument("--receipts", help="receipts dir")
    ap.add_argument("--launchd-log", help="the runner's cumulative log")
    ap.add_argument("--run-log", help="run-log.md")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("record")
    p.add_argument("--date")
    p.add_argument("--no-write", action="store_true")
    p = sub.add_parser("report")
    p.add_argument("--asof")
    p.add_argument("--window", type=int)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("history")
    p.add_argument("--json", action="store_true")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return cmd_selftest(None, a)
    e = Env(a)
    return {"record": cmd_record, "report": cmd_report, "history": cmd_history}[a.cmd](e, a)


if __name__ == "__main__":
    raise SystemExit(main())
