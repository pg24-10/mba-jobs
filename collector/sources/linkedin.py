"""LinkedIn, public guest pages only. No login, no cookies, no Voyager API.

Pacing: 2-3 s between requests with jitter, never under 1.5 s, and a short
break every few hundred requests. A 429/999 doubles the wait and rests for
5, 10, then 20 minutes; after `blocks_before_stop` blocks the run raises Blocked so
the caller can mark LinkedIn "pending" (keeping the jobs finished so far).
"""

import html
import random
import re
import time
from urllib.parse import parse_qs, urlparse

import requests

from ..net import online, wait_until_online
from ..settings import config
from . import Blocked, NetworkDown

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
COMPANY_URL = "https://www.linkedin.com/company/{slug}"
JOB_URL = "https://www.linkedin.com/jobs/view/{job_id}"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

try:
    import certifi
    _VERIFY = certifi.where()
except ImportError:
    _VERIFY = True


def _text(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def _grab(chunk, cls):
    m = re.search(r'class="[^"]*' + cls + r'[^"]*"[^>]*>(.*?)</', chunk, re.S)
    return _text(m.group(1)) if m else ""


def parse_cards(body):
    jobs = []
    for chunk in re.split(r"<li[ >]", body)[1:]:
        m = re.search(r"urn:li:jobPosting:(\d+)", chunk)
        if not m:
            continue
        company = _grab(chunk, "base-search-card__subtitle")
        slug = re.search(r'href="https://[a-z]+\.linkedin\.com/company/([^?"/]+)', chunk)
        posted = re.search(r'<time[^>]*datetime="([^"]+)"', chunk)
        jobs.append({
            "id": m.group(1),
            "title": _grab(chunk, "base-search-card__title"),
            "company": company,
            "company_slug": slug.group(1) if slug else "",
            "location": _grab(chunk, "job-search-card__location"),
            "posted": posted.group(1) if posted else None,
            "salary": _grab(chunk, "job-search-card__salary-info"),
        })
    return jobs


class LinkedIn:
    def __init__(self, log=print):
        s = config("settings")["linkedin"]
        self.delay = float(s["delay_seconds"])
        self.min_delay = float(s["min_delay_seconds"])
        self.max_pages = int(s["max_pages_per_search"])
        self.blocks_before_stop = int(s["blocks_before_stop"])
        self.block_rest = float(s.get("block_rest_minutes", 5)) * 60
        self.rest_every = int(s.get("rest_every_requests", 0))
        self.rest_minutes = float(s.get("rest_minutes", 0))
        self.offline_wait = float(s.get("offline_wait_minutes", 30)) * 60
        self.wait = self.delay
        self.blocks = 0
        self.requests = 0
        self.log = log
        self.http = requests.Session()
        self.http.verify = _VERIFY
        self.http.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._last = 0.0

    def _get(self, url, params=None):
        """GET with pacing and back-off. Returns body text, or None for a 4xx/5xx.
        A network drop waits for the internet; if it stays down, or LinkedIn stops
        answering, raises NetworkDown (never a silent "no results")."""
        timeouts = 0
        while True:
            pause = max(self.min_delay, self.wait + random.uniform(-0.5, 0.8))
            time.sleep(max(0.0, self._last + pause - time.time()))
            self._last = time.time()
            self.requests += 1
            if self.rest_every and self.requests % self.rest_every == 0:
                self.log(f"  {self.requests} LinkedIn requests: short {self.rest_minutes:.0f}-minute break")
                time.sleep(self.rest_minutes * 60)
            try:
                r = self.http.get(url, params=params, timeout=30)
            except requests.RequestException as e:
                self.log(f"  linkedin network error: {str(e)[:160]}")
                if not online():
                    if not wait_until_online(self.offline_wait, self.log):
                        raise NetworkDown(f"internet down for over {self.offline_wait / 60:.0f} min")
                    continue                                  # a drop doesn't count as a try
                timeouts += 1
                if timeouts >= 3:
                    raise NetworkDown(f"LinkedIn not answering: {str(e)[:160]}")
                time.sleep(5 * timeouts)
                continue
            if r.status_code in (429, 999):
                self.blocks += 1
                self.wait = min(self.wait * 2, 60)
                self.log(f"  linkedin pushed back ({r.status_code}), block {self.blocks}; waiting {self.wait:.0f}s between requests")
                if self.blocks >= self.blocks_before_stop:
                    raise Blocked(f"{self.blocks} blocks (last status {r.status_code})")
                rest = self.block_rest * 2 ** (self.blocks - 1)       # 5, 10, 20 minutes
                self.log(f"  resting {rest / 60:.0f} minutes before trying LinkedIn again")
                time.sleep(rest)
                continue
            if "authwall" in r.url:
                return None
            if r.status_code >= 400:
                return None
            # ease back towards the normal pace after a good response
            self.wait = max(self.delay, self.wait * 0.9)
            return r.text

    # ---------------------------------------------------------- search

    def search(self, keywords, location, seconds, extra=None):
        """Yield job cards for one search, paging by 10 until results run out."""
        seen = set()
        for page in range(self.max_pages):
            params = {"keywords": keywords, "location": location,
                      "f_TPR": f"r{int(seconds)}", "start": page * 10}
            params.update(extra or {})
            body = self._get(SEARCH_URL, params)
            cards = parse_cards(body) if body else []
            fresh = [c for c in cards if c["id"] not in seen]
            if not fresh:
                return
            for c in fresh:
                seen.add(c["id"])
                yield c

    def company_jobs(self, company_id, seconds):
        yield from self.search("", "India", seconds, extra={"f_C": company_id})

    # ---------------------------------------------------------- detail

    def detail(self, job_id):
        body = self._get(DETAIL_URL.format(job_id=job_id))
        if not body:
            return None
        m = re.search(r'class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', body, re.S)
        criteria = {
            _text(k): _text(v)
            for k, v in re.findall(
                r'description__job-criteria-subheader[^>]*>(.*?)</h3>.*?description__job-criteria-text[^>]*>(.*?)</span>',
                body, re.S)
        }
        # externally-applied jobs carry the offsite URL in a hidden <code id="applyUrl">
        code = re.search(r'<code id="applyUrl"[^>]*>\s*<!--\s*"?(.*?)"?\s*-->', body, re.S)
        offsite = bool(code) or bool(re.search(r'id="applyUrl"', body))
        caption = re.search(r'num-applicants__caption[^>]*>(.*?)</', body, re.S)
        return {
            "description": _text(m.group(1).replace("<br>", "\n").replace("</li>", "\n")) if m else "",
            "seniority": criteria.get("Seniority level"),
            "employment_type": criteria.get("Employment type"),
            "job_function": criteria.get("Job function"),
            "industry": criteria.get("Industries"),
            "apply_offsite": offsite,
            "apply_url": company_link(html.unescape(code.group(1))) if code else None,
            "applicants": applicants_of(_text(caption.group(1)) if caption else ""),
        }

    # ---------------------------------------------------------- companies

    def find_company(self, name):
        """Best-effort (slug, numeric id) for a company name, for the company sweep."""
        from ..text import company_key

        want = company_key(name)
        body = self._get(SEARCH_URL, {"keywords": name, "location": "India", "start": 0})
        slug = None
        for c in parse_cards(body or ""):
            if c["company_slug"] and company_key(c["company"]) == want:
                slug = c["company_slug"]
                break
        if not slug:
            return None, None
        page = self._get(COMPANY_URL.format(slug=slug)) or ""
        ids = re.findall(r"urn:li:(?:organization|company|fsd_company):(\d+)", page) + re.findall(r"f_C=(\d+)", page)
        if not ids:
            return slug, None
        return slug, max(set(ids), key=ids.count)


def company_link(url):
    """LinkedIn wraps offsite links as .../externalApply/...?url=<encoded>; return the inner one."""
    inner = parse_qs(urlparse(url).query).get("url")
    return inner[0] if inner and "linkedin.com" in (urlparse(url).hostname or "") else url


def applicants_of(caption):
    """'106 applicants' -> 106, 'Over 200 applicants' -> 200,
    'Be among the first 25 applicants' -> 25. A snapshot from when we fetched it."""
    m = re.search(r"([\d,]+)\s+applicant", caption or "", re.I)
    return int(m.group(1).replace(",", "")) if m else None


def to_raw(card, info=None):
    """Card (+ detail) -> the shared raw job shape the pipeline normalizes."""
    info = info or {}
    return {
        "source": "linkedin",
        "source_id": f"linkedin:{card['id']}",
        "url": JOB_URL.format(job_id=card["id"]),
        "title": card["title"],
        "company": card["company"],
        "location": card["location"],
        "posted_at": card.get("posted"),
        "description": info.get("description"),
        "employment_type": info.get("employment_type"),
        "industry": info.get("industry"),
        "salary_text": card.get("salary"),
        "apply_on_company_site": info.get("apply_offsite") if info else None,
        "applicants": info.get("applicants"),
        "apply_url": info.get("apply_url"),
    }
