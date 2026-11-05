"""Command line: `python -m collector.cli <command>` (or `mba-jobs <command>`)."""

import argparse
import sys

from .settings import config


def cmd_load_companies(args):
    from .companies import build_companies
    from .db import DB

    rows = build_companies()
    DB().upsert("companies", rows, on_conflict="company_key")
    print(f"companies: {len(rows)} loaded "
          f"({sum(r['in_lineup'] for r in rows)} in lineup, "
          f"{sum(r['in_isb_recruiters'] for r in rows)} past ISB recruiters, "
          f"{sum(r['in_watch_list'] for r in rows)} on the watch list)")


def cmd_discover_ats(args):
    from datetime import datetime, timezone

    from .db import DB
    from .sources.ats import ATS

    db = DB()
    rows = db.select("companies", {"select": "name,company_key,ats_type,discovered_at",
                                   "or": "(in_lineup.eq.true,in_watch_list.eq.true)"})
    todo = [r for r in rows if not r["ats_type"] and (args.again or not r["discovered_at"])]
    print(f"checking {len(todo)} companies for Greenhouse / Lever / Ashby boards")
    client, found = ATS(), 0
    for n, r in enumerate(todo, 1):
        ats_type, token = client.discover(r["company_key"], r["name"])
        db.update("companies", {"company_key": r["company_key"]},
                  {"ats_type": ats_type, "ats_token": token,
                   "discovered_at": datetime.now(timezone.utc).isoformat()})
        if ats_type:
            found += 1
            print(f"  {r['name']}: {ats_type} / {token}")
        if n % 25 == 0:
            print(f"  ...{n}/{len(todo)} checked, {found} boards found", flush=True)
    print(f"done: {found} boards found")


def cmd_learn_boards(args):
    """Seed careers pages now instead of waiting for daily runs: broad Indeed searches
    (no city filter), then read each job's company apply link."""
    import time

    from .db import DB
    from .pipeline import learn_boards
    from .sources import jobspy_sources

    db, raws = DB(), []
    groups = _pick(config("searches")["groups"], args.group, "id")
    for g in groups:
        found, errors = jobspy_sources.search("indeed", g["query"], "India", args.days * 24)
        raws += found
        print(f"  {g['id']}: {len(found)} Indeed jobs" + (f" ({len(errors)} page errors)" if errors else ""), flush=True)
        time.sleep(config("settings")["jobspy"]["delay_seconds"]["indeed"])
    print(f"done: {learn_boards(db, raws, print)} careers pages learned from {len(raws)} jobs")


def cmd_isb_coverage(args):
    """Which past ISB recruiters have jobs on the site, and which careers page we read.
    Written to data/reports/ (git-ignored: it lists ISB reference data)."""
    import csv
    from collections import Counter

    from .db import DB
    from .pipeline import load_isb
    from .settings import ROOT

    db = DB()
    isb = load_isb(db)
    companies = db.select("companies", {"select": "name,company_key,in_lineup,ats_type,ats_token",
                                        "in_isb_recruiters": "eq.true"})
    jobs = db.select("jobs", {"select": "company,sources", "past_isb_recruiter": "eq.true"})
    found, by_source = Counter(), {}
    for j in jobs:
        key = isb.which(j["company"])
        if key:
            found[key] += 1
            by_source.setdefault(key, Counter()).update(j["sources"] or [])
    rows = sorted(companies, key=lambda c: (found[c["company_key"]] > 0, not c["in_lineup"], c["name"].lower()))
    out = ROOT / "data" / "reports" / "isb-coverage.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["company", "jobs found", "found on", "careers page", "in campus lineup"])
        for c in rows:
            k = c["company_key"]
            page = "" if c["ats_type"] in (None, "none") else f"{c['ats_type']}: {c['ats_token']}"
            w.writerow([c["name"], found[k], ", ".join(sorted(by_source.get(k, {}))), page,
                        "yes" if c["in_lineup"] else ""])
    hit = sum(1 for c in companies if found[c["company_key"]])
    lineup = [c for c in companies if c["in_lineup"]]
    pages = sum(1 for c in companies if c["ats_type"] not in (None, "none"))
    print(f"past ISB recruiters: {len(companies)}")
    print(f"  with at least one job on the site: {hit} ({hit / max(len(companies), 1):.0%})")
    print(f"  also in the campus lineup: {len(lineup)}, of which with jobs: "
          f"{sum(1 for c in lineup if found[c['company_key']])}")
    print(f"  careers page read directly: {pages}")
    print(f"  {len(jobs)} ISB jobs in all; full list (gaps first): {out}")


def _pick(items, wanted, field):
    if not wanted:
        return items
    picked = [i for i in items if i[field] in wanted]
    missing = set(wanted) - {i[field] for i in picked}
    if missing:
        sys.exit(f"unknown {field}: {', '.join(sorted(missing))}")
    return picked


def cmd_collect(args):
    from .db import DB
    from .pipeline import run

    s = config("searches")
    groups = _pick(s["groups"], args.group, "id")
    locations = _pick(s["locations"], args.city, "name")
    summary = run(DB(), args.sources, groups, locations, days=args.days)
    failed = [k for k, v in summary.items() if v["status"] == "failed"]
    sys.exit(1 if failed and len(failed) == len(summary) else 0)


def cmd_backfill(args):
    from .backfill import backfill
    from .db import DB

    s = config("searches")
    groups = _pick(s["groups"], args.group, "id")
    locations = _pick(s["locations"], args.city, "name")
    done = backfill(DB(), args.sources, groups, locations, days=args.days, restart=args.restart)
    sys.exit(0 if done else 2)


def main(argv=None):
    p = argparse.ArgumentParser(prog="mba-jobs")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover-ats", help="find lineup/watch-list companies' public job boards")
    d.add_argument("--again", action="store_true", help="re-check companies already checked")
    d.set_defaults(fn=cmd_discover_ats)
    lb = sub.add_parser("learn-boards", help="find careers pages from Indeed apply links")
    lb.add_argument("--days", type=float, default=30)
    lb.add_argument("--group", nargs="+", help="search group ids (default: all)")
    lb.set_defaults(fn=cmd_learn_boards)
    sub.add_parser("isb-coverage", help="which past ISB recruiters have jobs (report in data/reports/)").set_defaults(fn=cmd_isb_coverage)
    sub.add_parser("load-companies", help="load reference spreadsheets + watch list into Supabase").set_defaults(fn=cmd_load_companies)

    for name, sources, helptext in [
        ("daily", ["linkedin", "indeed", "naukri", "iimjobs", "ats"], "the daily run (catches up from the last success)"),
        ("linkedin", ["linkedin"], "LinkedIn only (the Mac fallback)"),
        ("collect", ["linkedin", "indeed", "naukri", "iimjobs"], "custom run, e.g. a small test"),
    ]:
        c = sub.add_parser(name, help=helptext)
        c.add_argument("--sources", nargs="+", default=sources)
        c.add_argument("--group", nargs="+", help="search group ids (default: all)")
        c.add_argument("--city", nargs="+", help="location names (default: all)")
        c.add_argument("--days", type=float, help="fixed window in days instead of catching up")
        c.set_defaults(fn=cmd_collect)

    b = sub.add_parser("backfill", help="one-time catch-up of the last N days (resumable)")
    b.add_argument("--days", type=float, default=30)
    b.add_argument("--sources", nargs="+", default=["iimjobs", "indeed", "linkedin", "ats"])  # Naukri: daily runs only (5 Nov 2026)
    b.add_argument("--group", nargs="+", help="search group ids (default: all)")
    b.add_argument("--city", nargs="+", help="location names (default: all)")
    b.add_argument("--restart", action="store_true", help="forget the checkpoint and start over")
    b.set_defaults(fn=cmd_backfill)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
