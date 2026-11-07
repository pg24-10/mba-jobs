"""Hands-off LinkedIn backfill (added 7 Nov 2026): leave the laptop open and run

    caffeinate -i .venv/bin/python -u -m collector.cli backfill-auto

1. Runs the backfill steps (search cards only). When LinkedIn pauses it for the
   session, rests an hour and carries on, until every step is done.
2. Then opens the job pages Claude marked "open" (fill-details), one at a time.
   Claude sorts the queue in a scheduled task every hour (ops/triage-task-prompt.md);
   when nothing is left to open but cards are still waiting to be sorted, this
   waits for Claude and checks again every 30 minutes.

Only one thing talks to LinkedIn at a time: the steps first, then the pages.
"""

import time

from . import triage
from .backfill import backfill

SESSION_REST = 60 * 60       # LinkedIn paused the backfill: rest this long before the next session
MAX_SESSIONS = 12            # stop trying after this many (steps that keep failing need a look)
SORT_WAIT = 30 * 60          # waiting for Claude to sort more cards
MAX_SORT_WAIT = 24 * 60 * 60 # ...for at most a day with no sorting progress


def unfilled():
    q, d = triage.load_queue(), triage.load_decisions()
    return sum(v.get("decision") == "open" and not v.get("filled") and i in q for i, v in d.items())


def run_auto(db, groups=None, locations=None, days=30, log=print, sleep=time.sleep):
    for session in range(1, MAX_SESSIONS + 1):
        if backfill(db, ["linkedin"], groups, locations, days=days, log=log):
            break
        if session == MAX_SESSIONS:
            log(f"\nauto: backfill still has steps left after {MAX_SESSIONS} sessions; "
                "moving on to job pages. Run backfill again later for the rest.")
            break
        log(f"\nauto: resting {SESSION_REST // 60} min before the next backfill session ({session}/{MAX_SESSIONS})")
        sleep(SESSION_REST)

    waited, last_to_sort = 0, None
    while True:
        s = triage.status()
        if unfilled():
            result = triage.fill_details(db, log=log)
            if result["stopped"]:
                log(f"auto: resting {SESSION_REST // 60} min before opening more job pages")
                sleep(SESSION_REST)
            continue
        if not s["to_sort"]:
            log(f"\nauto: all done. {s['open']} jobs opened, {s['skip']} skipped by Claude.")
            return True
        if s["to_sort"] != last_to_sort:           # Claude sorted some since the last check
            waited, last_to_sort = 0, s["to_sort"]
        if waited >= MAX_SORT_WAIT:
            log(f"auto: {s['to_sort']} cards still unsorted after a day with no progress. "
                "Is the hourly sorting task running in the Claude app? Stopping here; "
                "run backfill-auto again once they are sorted.")
            return False
        log(f"auto: {s['to_sort']} cards waiting for Claude to sort; checking again in {SORT_WAIT // 60} min")
        sleep(SORT_WAIT)
        waited += SORT_WAIT
