"""`mba-jobs coverage`: do we have the roles ISB students actually got on campus?

For each campus role (reference/campus_roles.xlsx) it looks for jobs at the same
company (see same_company: "Accenture Solutions Pvt Ltd" on the campus list is
"Accenture" on job sites) and compares titles. Each role is reported as
  found         a job at that company with a similar title
  company only  jobs at that company, none with a similar title
  missing       no jobs at that company at all
The report goes to data/reports/coverage.csv (git-ignored: it lists ISB data).
Campus roles are often filled months before we look, so "company only" is a
fair result; "missing" points at companies the searches or watch list miss.
"""

import csv

from rapidfuzz import fuzz

from .settings import ROOT
from .text import company_key, title_key

SIMILAR = 70          # rapidfuzz token_set_ratio between the two titles


def same_company(campus_key, job_key):
    """Same key, or one is the other plus more words: "accenture" and
    "accenture solutions", "ey" and "ey parthenon". "jsw paints" and "jsw steel"
    are different companies."""
    a, b = campus_key.split(), job_key.split()
    n = min(len(a), len(b))
    return n > 0 and a[:n] == b[:n]


def company_jobs(db, key):
    """Jobs (stale ones too) at this company (see same_company)."""
    if not key:
        return []
    first = key.split()[0]
    rows = db.select("jobs", {"select": "title,company,company_key,sources,is_stale",
                              "company_key": f"like.{first}*"})
    return [r for r in rows if same_company(key, r["company_key"])]


def best_title(title, jobs):
    t = title_key(title)
    scored = [(fuzz.token_set_ratio(t, title_key(j["title"])), j) for j in jobs]
    return max(scored, key=lambda x: x[0], default=(0, None))


def check(roles, lookup):
    """roles: [{company, title}]; lookup(company_key) -> jobs. Returns report rows."""
    cache, out = {}, []
    for r in roles:
        key = company_key(r["company"])
        if key not in cache:
            cache[key] = lookup(key)
        jobs = cache[key]
        score, job = best_title(r["title"], jobs)
        result = "found" if score >= SIMILAR else ("company only" if jobs else "missing")
        out.append({"company": r["company"], "campus title": r["title"], "result": result,
                    "jobs at company": len(jobs),
                    "closest title": job["title"] if job else "", "similarity": round(score),
                    "found on": ", ".join(sorted(set(job["sources"] or []))) if job else ""})
    return out


def run(db, roles, log=print):
    rows = check(roles, lambda k: company_jobs(db, k))
    path = ROOT / "data" / "reports" / "coverage.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    order = {"missing": 0, "company only": 1, "found": 2}
    rows.sort(key=lambda r: (order[r["result"]], r["company"].lower()))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    n = len(rows)
    count = {k: sum(r["result"] == k for r in rows) for k in order}
    companies = {company_key(r["company"]) for r in rows}
    with_jobs = {company_key(r["company"]) for r in rows if r["result"] != "missing"}
    log(f"campus roles: {n}")
    log(f"  found (similar title at the same company): {count['found']} ({count['found'] / n:.0%})")
    log(f"  company has jobs, not this title:          {count['company only']} ({count['company only'] / n:.0%})")
    log(f"  company not on the site:                   {count['missing']} ({count['missing'] / n:.0%})")
    log(f"  companies with jobs: {len(with_jobs)} of {len(companies)}")
    log(f"  full list (misses first): {path}")
    return rows
