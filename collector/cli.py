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


def main(argv=None):
    p = argparse.ArgumentParser(prog="mba-jobs")
    sub = p.add_subparsers(dest="command", required=True)

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

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
