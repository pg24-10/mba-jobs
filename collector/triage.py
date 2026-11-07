"""Cards first, Claude decides, then open only what is worth it (added 7 Nov 2026).

The LinkedIn backfill saves each job from its search card (title, company, city,
date, link) without opening the job page. The cards it would have opened go into
a local queue. Claude reads them (`triage-export` -> CSV), marks each one "open"
or "skip" (`triage-import`), and `fill-details` opens only the "open" ones, at
the usual LinkedIn pace, and adds their descriptions.

Everything here lives in data/state/triage/ (git-ignored):
  queue.jsonl     one card per line, as the backfill found it
  decisions.json  {linkedin id: {"decision", "reason", "at", "filled"}}
"""

import csv
import fcntl
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from .settings import STATE

DIR = STATE / "triage"
QUEUE = DIR / "queue.jsonl"
DECISIONS = DIR / "decisions.json"
CHOICES = ("open", "skip")
CARD_FIELDS = ("id", "title", "company", "company_slug", "location", "posted", "salary", "search_city")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _locked():
    """Two backfill windows (or a backfill and fill-details) may touch these files."""
    DIR.mkdir(parents=True, exist_ok=True)
    with open(DIR / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# ------------------------------------------------------------------ queue

def queue_cards(cards):
    """Add cards (dicts from linkedin.parse_cards + search_city) to the queue."""
    if not cards:
        return
    with _locked(), open(QUEUE, "a", encoding="utf-8") as f:
        for c in cards:
            f.write(json.dumps({k: c.get(k) for k in CARD_FIELDS}, ensure_ascii=False) + "\n")


def load_queue():
    """{id: card}; a card found again later replaces the earlier copy."""
    out = {}
    if QUEUE.exists():
        for line in QUEUE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                out[c["id"]] = c
    return out


def load_decisions():
    return json.loads(DECISIONS.read_text()) if DECISIONS.exists() else {}


def _save_decisions(d):
    tmp = DECISIONS.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    tmp.replace(DECISIONS)


def update_decisions(changes):
    """Merge {id: {field: value}} into decisions.json under the lock."""
    with _locked():
        d = load_decisions()
        for i, fields in changes.items():
            d.setdefault(i, {}).update(fields)
        _save_decisions(d)
        return d


def status():
    q, d = load_queue(), load_decisions()
    opened = [i for i, v in d.items() if v.get("decision") == "open"]
    return {
        "queued": len(q),
        "to_sort": sum(i not in d or "decision" not in d[i] for i in q),
        "open": len(opened),
        "skip": sum(v.get("decision") == "skip" for v in d.values()),
        "filled": sum(bool(d[i].get("filled")) for i in opened),
    }


# ------------------------------------------------------------------ Claude's part

def export(path, limit=None):
    """Write the cards still to sort to a CSV for Claude. Returns how many."""
    q, d = load_queue(), load_decisions()
    todo = [c for i, c in q.items() if "decision" not in d.get(i, {})]
    todo.sort(key=lambda c: (c.get("search_city") or "", c.get("company") or "", c.get("title") or ""))
    if limit:
        todo = todo[:limit]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "title", "company", "city", "location", "posted", "decision", "reason"])
        for c in todo:
            w.writerow([c["id"], c.get("title"), c.get("company"), c.get("search_city"),
                        c.get("location"), (c.get("posted") or "")[:10], "", ""])
    return len(todo)


def import_decisions(path):
    """Read Claude's CSV (id, decision, reason; other columns ignored).
    Returns (saved, problems) where problems lists rows that were not understood."""
    q = load_queue()
    changes, problems = {}, []
    with open(path, newline="", encoding="utf-8") as f:
        for n, row in enumerate(csv.DictReader(f), 2):
            i = (row.get("id") or "").strip()
            choice = (row.get("decision") or "").strip().lower()
            if not choice:
                continue                                  # not sorted yet
            if i not in q or choice not in CHOICES:
                problems.append(f"line {n}: id {i!r}, decision {choice!r}")
                continue
            changes[i] = {"decision": choice, "reason": (row.get("reason") or "").strip()[:200],
                          "at": _now()}
    if changes:
        update_decisions(changes)
    return len(changes), problems


# ------------------------------------------------------------------ open the chosen ones

def fill_details(db, limit=None, log=print, batch=25):
    """Open the "open" jobs not filled yet, add their page details, save in batches.
    Stops (keeping everything saved) when LinkedIn blocks or the internet stays down."""
    from .pipeline import inbox_item, load_isb, merge, normalize, save, write_inbox
    from .sources import Blocked, NetworkDown
    from .sources.linkedin import LinkedIn, to_raw

    q, d = load_queue(), load_decisions()
    todo = [i for i, v in d.items() if v.get("decision") == "open" and not v.get("filled") and i in q]
    if limit:
        todo = todo[:limit]
    log(f"fill-details: {len(todo)} jobs to open")
    if not todo:
        return {"opened": 0, "left": 0, "stopped": None}
    li, isb = LinkedIn(log=log), load_isb(db)
    raws, done, opened, stopped = [], {}, 0, None

    def flush():
        rows = [r for r in (normalize(raw, isb)[0] for raw in raws) if r]
        merged = merge(rows)
        saved = save(db, merged, "linkedin", log) if merged else []
        by_key = {r["dedupe_key"]: r for r in merged}
        write_inbox([inbox_item(by_key[r["dedupe_key"]], r["id"]) for r in saved
                     if by_key[r["dedupe_key"]]["description_trimmed"]])
        update_decisions(done)
        raws.clear()
        done.clear()

    for i in todo:
        try:
            info = li.detail(i)
        except (Blocked, NetworkDown) as e:
            stopped = f"{type(e).__name__}: {e}"
            log(f"  stopped: {stopped}. Run fill-details again later; it carries on from here.")
            break
        card = q[i]
        raw = to_raw(card, info)
        raw["search_city"] = card.get("search_city")
        raws.append(raw)
        done[i] = {"filled": _now() if info else "no page"}
        opened += 1
        if len(raws) >= batch:
            flush()
            log(f"  {opened}/{len(todo)} opened ({li.requests} requests, {li.blocks} push-backs)")
    if raws:
        flush()
    log(f"fill-details: {opened} opened, {len(todo) - opened} left")
    return {"opened": opened, "left": len(todo) - opened, "stopped": stopped}
