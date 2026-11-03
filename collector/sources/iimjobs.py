"""IIMjobs: the JSON feed behind its public search page (plain requests, no login).

robots.txt asks for 10 seconds between requests, so that is the pace. The feed
has no description; IIMjobs' own role tags are passed to Claude instead.
"""

import time
from datetime import datetime, timezone

import requests

from ..settings import config

SEARCH_URL = "https://gladiator.iimjobs.com/job/search"
POSTING_DAYS = [1, 3, 7, 15, 30]          # the site's "posted in last N days" choices

try:
    import certifi
    _VERIFY = certifi.where()
except ImportError:
    _VERIFY = True


class IIMJobs:
    def __init__(self, log=print):
        self.delay = float(config("settings")["iimjobs"]["delay_seconds"])
        self.max_pages = int(config("settings")["iimjobs"]["max_pages_per_search"])
        self.http = requests.Session()
        self.http.verify = _VERIFY
        self.http.headers["User-Agent"] = "mba-jobs/1.0 (job aggregator for students)"
        self.log = log
        self.requests = 0
        self._last = 0.0

    def _get(self, params):
        time.sleep(max(0.0, self._last + self.delay - time.time()))
        self._last = time.time()
        self.requests += 1
        r = self.http.get(SEARCH_URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def search(self, term, since):
        """All jobs for one phrase posted since `since` (aware datetime)."""
        days = (datetime.now(timezone.utc) - since).total_seconds() / 86400
        posting = next((d for d in POSTING_DAYS if d >= days), POSTING_DAYS[-1])
        cutoff = since.timestamp() * 1000
        out = []
        for page in range(self.max_pages):
            data = self._get({"query": term.replace('"', ""), "page": page,
                              "posting": posting, "industry": ""})
            jobs = data.get("data") or []
            out += [j for j in jobs if (j.get("createdTimeMs") or 0) >= cutoff]
            if not data.get("hasMore") or not jobs:
                break
        return out


def to_raw(job):
    company = ((job.get("companyData") or {}).get("companyName") or "").strip()
    title = (job.get("jobdesignation") or "").strip()
    if not title:                                   # "Paytm - Product Manager"
        title = job.get("title", "")
        if company and title.lower().startswith(company.lower() + " - "):
            title = title[len(company) + 3:]
    locations = [l.get("name") for l in job.get("locations") or [] if l.get("name")]
    if job.get("otherLocation"):
        locations.append(job["otherLocation"])
    tags = ", ".join(t.get("name") for t in job.get("tags") or [] if t.get("name"))
    # minSal/maxSal are already lakhs a year (checked 3 Nov 2026: 3-8 yrs -> 15-22); 99 is the top of their scale
    show_salary = not job.get("hideSal") and (job.get("minSal") or job.get("maxSal"))
    posted = job.get("createdTimeMs")
    return {
        "source": "iimjobs",
        "source_id": f"iimjobs:{job['id']}",
        "url": job.get("jobDetailUrl"),
        "title": title,
        "company": company if not job.get("confidential") else "",
        "location": " / ".join(locations),
        "locations": locations,
        "posted_at": datetime.fromtimestamp(posted / 1000, timezone.utc).isoformat() if posted else None,
        "description": f"IIMjobs role tags: {tags}" if tags else None,
        "experience_min": job.get("min"),
        "experience_max": job.get("max"),
        "salary_min_lpa": job.get("minSal") if show_salary else None,
        "salary_max_lpa": job.get("maxSal") if show_salary else None,
        "work_mode_hint": "remote" if job.get("workFromHome") else None,
        "apply_on_company_site": bool(job.get("applyUrl")) or None,
    }
