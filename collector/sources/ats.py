"""Company career pages on Greenhouse, Lever and Ashby (their public job-board APIs).

Each company in `companies` with ats_type + ats_token is fetched once per run;
only India (or remote-India) jobs inside the window are kept.
"""

import time
from datetime import datetime, timezone

import requests

from ..settings import config
from ..text import fold

try:
    import certifi
    _VERIFY = certifi.where()
except ImportError:
    _VERIFY = True

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true",
}

INDIA_WORDS = ["india", "bangalore", "bengaluru", "mumbai", "delhi", "gurugram", "gurgaon",
               "noida", "hyderabad", "pune", "chennai", "kolkata"]


def in_india(location):
    text = fold(location)
    return any(w in text for w in INDIA_WORDS)


def _when(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):          # Lever: milliseconds
        return datetime.fromtimestamp(value / 1000, timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class ATS:
    def __init__(self, log=print):
        self.delay = float(config("settings")["ats"]["delay_seconds"])
        self.http = requests.Session()
        self.http.verify = _VERIFY
        self.http.headers["User-Agent"] = "mba-jobs/1.0 (job aggregator for students)"
        self.log = log
        self._last = 0.0

    def _get(self, url):
        time.sleep(max(0.0, self._last + self.delay - time.time()))
        self._last = time.time()
        r = self.http.get(url, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def fetch(self, company, ats_type, token, since):
        """India jobs for one company posted/updated since `since` (aware datetime)."""
        data = self._get(URLS[ats_type].format(token=token))
        if data is None:
            return []
        jobs = []
        for j in self._parse(ats_type, data):
            if not in_india(j["location"]):
                continue
            posted = _when(j.pop("_when"))
            if posted and since and posted < since:
                continue
            j.update(source="ats", company=company,
                     posted_at=posted.isoformat() if posted else None,
                     source_id=f"{ats_type}:{token}:{j.pop('_id')}",
                     apply_on_company_site=True)
            jobs.append(j)
        return jobs

    @staticmethod
    def _parse(ats_type, data):
        if ats_type == "greenhouse":
            for j in data.get("jobs", []):
                yield {"_id": j["id"], "_when": j.get("first_published") or j.get("updated_at"),
                       "title": j.get("title", ""), "url": j.get("absolute_url"),
                       "location": (j.get("location") or {}).get("name", ""),
                       "description": j.get("content")}
        elif ats_type == "lever":
            for j in data:
                cat = j.get("categories") or {}
                locs = [cat.get("location") or ""] + list(cat.get("allLocations") or [])
                yield {"_id": j["id"], "_when": j.get("createdAt"),
                       "title": j.get("text", ""), "url": j.get("hostedUrl"),
                       "location": " / ".join(l for l in locs if l),
                       "employment_type": cat.get("commitment"),
                       "work_mode_hint": j.get("workplaceType"),
                       "description": " ".join([j.get("descriptionPlain") or ""] +
                                               [l.get("content", "") for l in j.get("lists") or []])}
        elif ats_type == "ashby":
            for j in data.get("jobs", []):
                locs = [j.get("location") or ""] + [
                    (a.get("location") or "") for a in j.get("secondaryLocations") or []]
                yield {"_id": j.get("id"), "_when": j.get("publishedAt"),
                       "title": j.get("title", ""), "url": j.get("jobUrl"),
                       "location": " / ".join(l for l in locs if l),
                       "employment_type": j.get("employmentType"),
                       "work_mode_hint": "remote" if j.get("isRemote") else j.get("workplaceType"),
                       "description": j.get("descriptionPlain")}

    def discover(self, company_key, name):
        """Phase 2: guess a board token from the company name and see if it answers."""
        guesses = {company_key.replace(" ", ""), company_key.replace(" ", "-"),
                   fold(name).split()[0] if name else ""}
        for ats_type in URLS:
            for token in filter(None, guesses):
                try:
                    data = self._get(URLS[ats_type].format(token=token))
                except requests.RequestException:
                    continue
                if data and (data.get("jobs") if isinstance(data, dict) else data):
                    return ats_type, token
        return None, None
