"""One-time backfill: the last N days, every source, group and city.

Work is split into small steps (one source + group + city, or one IIMjobs
phrase group, or the company boards). After each step the checkpoint file
`data/state/backfill.json` is updated, so stopping and restarting carries on
from the next step. The window start is fixed on the first run, so a restart
the next night still covers the same 30 days.
"""

import fcntl
import json
import os
import time
from datetime import datetime, timedelta, timezone

from .net import online
from .pipeline import load_isb, run
from .settings import STATE, config

CHECKPOINT = STATE / "backfill.json"
ORDER = ["iimjobs", "naukri", "indeed", "linkedin", "ats"]   # quick sources first; careers pages last, so
                                                             # pages learned from apply links on the way are read too
FAILS_IN_A_ROW = 3        # a source failing this many steps with the internet up is blocking us: pause it
CHECK_EVERY = 60          # seconds between internet checks while offline
BLOCK_REST = 60 * 60      # a site pushed back (captcha, 429): rest this long, then retry the step
BLOCK_RETRIES = 3         # ...this many times before pausing the source for the session


def steps(sources, groups, locations):
    """(step key, source, groups, locations) in the order they run."""
    out = []
    for source in [s for s in ORDER if s in sources]:
        if source == "ats":
            out.append(("ats", source, groups, locations))
        elif source == "iimjobs":                  # IIMjobs searches all of India at once
            out += [(f"iimjobs|{g['id']}", source, [g], locations) for g in groups]
        else:
            out += [(f"{source}|{g['id']}|{loc['name']}", source, [g], [loc])
                    for g in groups for loc in locations]
    return out


def load_checkpoint(days, restart):
    if CHECKPOINT.exists() and not restart:
        state = json.loads(CHECKPOINT.read_text())
        state.setdefault("done", [])
        return state
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return {"since": since.isoformat(), "days": days, "done": [], "seconds": {}}


def save_checkpoint(state):
    """Write the checkpoint, keeping steps another backfill window (e.g. LinkedIn
    and Naukri run side by side) finished meanwhile."""
    STATE.mkdir(parents=True, exist_ok=True)
    with open(STATE / "backfill.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if CHECKPOINT.exists():
            disk = json.loads(CHECKPOINT.read_text())
            if disk.get("since") == state["since"]:
                state["done"] += [k for k in disk.get("done", []) if k not in state["done"]]
                for source, times in disk.get("seconds", {}).items():
                    if len(times) > len(state["seconds"].get(source, [])):
                        state["seconds"][source] = times
        tmp = CHECKPOINT.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(state, indent=1))
        tmp.replace(CHECKPOINT)


def timing_key(source, linkedin_details=True):
    """LinkedIn steps that only read search cards are timed apart from full ones."""
    return "linkedin-cards" if source == "linkedin" and not linkedin_details else source


def eta(state, todo, linkedin_details=True):
    """Rough time left from the average step time of each source so far."""
    left = 0.0
    for key, source, *_ in todo:
        times = state["seconds"].get(timing_key(source, linkedin_details)) or []
        left += sum(times) / len(times) if times else 0
    return left


def wait_for_internet(log, sleep=time.sleep):
    """Block until the internet is back, checking every minute."""
    log("  the internet seems to be down; waiting for it to come back (checking every minute)")
    t0 = time.time()
    while not online():
        sleep(CHECK_EVERY)
    log(f"  internet is back after {fmt(time.time() - t0)}; trying this step again")


def fmt(seconds):
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def backfill(db, sources, groups=None, locations=None, days=30, restart=False, log=print):
    searches = config("searches")
    groups = groups or searches["groups"]
    locations = locations or searches["locations"]
    settings = config("settings").get("backfill", {})
    skipped = set(settings.get("skip_locations", []))
    locations = [loc for loc in locations if loc["name"] not in skipped]
    state = load_checkpoint(days, restart)
    since = datetime.fromisoformat(state["since"])
    if settings.get("window_days"):                # steps still to run look back only this far;
        recent = datetime.now(timezone.utc) - timedelta(days=settings["window_days"])
        since = max(since, recent)                 # jobs already saved are kept as they are
    details = settings.get("linkedin_details", True)
    plan = steps(sources, groups, locations)
    todo = [s for s in plan if s[0] not in state["done"]]
    log(f"backfill since {since:%Y-%m-%d %H:%M} UTC: {len(plan)} steps, "
        f"{len(plan) - len(todo)} already done, {len(todo)} to go"
        + (f" (skipping {', '.join(sorted(skipped))})" if skipped else "")
        + ("" if details or "linkedin" not in sources else
           "; LinkedIn: search cards only, job pages queued for Claude to sort"))
    save_checkpoint(state)

    isb = load_isb(db)
    skip, totals, fails = set(), {"new": 0, "failed": 0}, {}
    for n, (key, source, g, locs) in enumerate(todo, 1):
        if source in skip:
            continue
        log(f"\n[{n}/{len(todo)}] {key}")
        t0, rested = time.time(), 0
        for attempt in range(BLOCK_RETRIES + 1):
            for _ in range(3):                        # an internet drop doesn't use up the step
                summary = run(db, [source], g, locs, since=since, isb=isb, log=log,
                              linkedin_details=details)[source]
                if summary["status"] in ("success", "pending") or online():
                    break
                wait_for_internet(log)
            if summary["status"] != "pending" or attempt == BLOCK_RETRIES:
                break
            log(f"  {source} pushed back; resting {BLOCK_REST // 60} min, then trying this step again "
                f"({attempt + 1}/{BLOCK_RETRIES})")
            time.sleep(BLOCK_REST)
            rested += BLOCK_REST
        took = time.time() - t0 - rested
        totals["new"] += summary["new"]

        fails[source] = 0 if summary["status"] == "success" else fails.get(source, 0) + 1
        if summary["status"] == "success":
            state["done"].append(key)
            state["seconds"].setdefault(timing_key(source, details), []).append(round(took))
        elif summary["status"] == "pending":          # LinkedIn pushed back: stop it, keep the rest
            skip.add(source)
            log(f"  {source} paused for this session; run the backfill again later to continue it")
        else:
            totals["failed"] += 1                     # left undone, retried next time
            if fails[source] >= FAILS_IN_A_ROW:       # e.g. Naukri asking for a captcha: stop knocking
                skip.add(source)
                log(f"  {source} failed {fails[source]} steps in a row; paused for this session. "
                    f"Run the backfill again later (a few hours) to continue it")
        save_checkpoint(state)

        remaining = [s for s in todo[n:] if s[1] not in skip]
        done = sum(k in state["done"] for k, *_ in plan)
        log(f"  step took {fmt(took)}; {done}/{len(plan)} steps done; "
            f"about {fmt(eta(state, remaining, details))} left "
            f"(finish near {datetime.now() + timedelta(seconds=eta(state, remaining, details)):%a %H:%M})")

    left = [s for s in plan if s[0] not in state["done"]]
    log(f"\nbackfill: {totals['new']} new jobs this session, {totals['failed']} steps failed, "
        f"{len(left)} steps left" + (" - run the same command again to finish them" if left else " - complete"))
    return not left
