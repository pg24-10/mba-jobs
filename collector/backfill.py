"""One-time backfill: the last N days, every source, group and city.

Work is split into small steps (one source + group + city, or one IIMjobs
phrase group, or the company boards). After each step the checkpoint file
`data/state/backfill.json` is updated, so stopping and restarting carries on
from the next step. The window start is fixed on the first run, so a restart
the next night still covers the same 30 days.
"""

import json
import time
from datetime import datetime, timedelta, timezone

from .pipeline import load_isb, run
from .settings import STATE, config

CHECKPOINT = STATE / "backfill.json"
ORDER = ["iimjobs", "naukri", "indeed", "linkedin", "ats"]   # quick sources first; careers pages last, so
                                                             # pages learned from apply links on the way are read too


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
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(CHECKPOINT)


def eta(state, todo):
    """Rough time left from the average step time of each source so far."""
    left = 0.0
    for key, source, *_ in todo:
        times = state["seconds"].get(source) or []
        left += sum(times) / len(times) if times else 0
    return left


def fmt(seconds):
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def backfill(db, sources, groups=None, locations=None, days=30, restart=False, log=print):
    searches = config("searches")
    groups = groups or searches["groups"]
    locations = locations or searches["locations"]
    state = load_checkpoint(days, restart)
    since = datetime.fromisoformat(state["since"])
    plan = steps(sources, groups, locations)
    todo = [s for s in plan if s[0] not in state["done"]]
    log(f"backfill since {since:%Y-%m-%d %H:%M} UTC: {len(plan)} steps, "
        f"{len(plan) - len(todo)} already done, {len(todo)} to go")
    save_checkpoint(state)

    isb = load_isb(db)
    skip, totals = set(), {"new": 0, "failed": 0}
    for n, (key, source, g, locs) in enumerate(todo, 1):
        if source in skip:
            continue
        log(f"\n[{n}/{len(todo)}] {key}")
        t0 = time.time()
        summary = run(db, [source], g, locs, since=since, isb=isb, log=log)[source]
        took = time.time() - t0
        totals["new"] += summary["new"]

        if summary["status"] == "success":
            state["done"].append(key)
            state["seconds"].setdefault(source, []).append(round(took))
        elif summary["status"] == "pending":          # LinkedIn pushed back: stop it, keep the rest
            skip.add(source)
            log(f"  {source} paused for this session; run the backfill again later to continue it")
        else:
            totals["failed"] += 1                     # left undone, retried next time
        save_checkpoint(state)

        remaining = [s for s in todo[n:] if s[1] not in skip]
        log(f"  step took {fmt(took)}; {len(state['done'])}/{len(plan)} steps done; "
            f"about {fmt(eta(state, remaining))} left "
            f"(finish near {datetime.now() + timedelta(seconds=eta(state, remaining)):%a %H:%M})")

    left = [s for s in plan if s[0] not in state["done"]]
    log(f"\nbackfill: {totals['new']} new jobs this session, {totals['failed']} steps failed, "
        f"{len(left)} steps left" + (" - run the same command again to finish them" if left else " - complete"))
    return not left
