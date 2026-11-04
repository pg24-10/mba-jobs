"""Indeed and Naukri through the JobSpy library (public search pages, no login)."""

import logging
import math
import random
import re
import time

from ..settings import config
from . import Blocked
from ..text import experience_range, to_lpa


def split_or(query):
    """'"product manager" OR strategy' -> ['"product manager"', 'strategy']."""
    return [p.strip() for p in re.split(r"\s+OR\s+", query) if p.strip()]


def terms_for(source, query):
    return [query] if config("searches")["supports_or"].get(source) else split_or(query)


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text if text and text.lower() not in ("nan", "none", "nat") else None


class _Errors(logging.Handler):
    """JobSpy logs page failures and returns what it has; collect them so a
    half-finished search is not mistaken for a complete one."""

    def __init__(self):
        super().__init__(logging.ERROR)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def search(source, term, location, hours, results_wanted=1000):
    """One JobSpy search. Returns (raw job dicts in the shared shape, error messages)."""
    from jobspy import scrape_jobs

    errors = _Errors()
    logger = logging.getLogger("jobspy")
    logger.addHandler(errors)
    try:
        df = _scrape(scrape_jobs, source, term, location, hours, results_wanted)
    finally:
        logger.removeHandler(errors)
    return [to_raw(source, row) for row in df.to_dict("records")], errors.messages


def _scrape(scrape_jobs, source, term, location, hours, results_wanted):
    return scrape_jobs(
        site_name=[source],
        search_term=term.replace('"', "") if source == "naukri" else term,
        location=location,
        results_wanted=results_wanted,
        country_indeed="india",
        hours_old=max(24, int(hours)),
        # JobSpy opens every Naukri job page back to back, which Naukri answers with a
        # captcha; NaukriPages opens only the ones we need, one at a time
        fetch_description=source != "naukri",
        description_format="markdown",
        verbose=0,
    )


def to_raw(source, row):
    get = lambda k: _clean(row.get(k))
    currency = get("currency") or "INR"
    interval = get("interval") or "yearly"
    lo, hi = to_lpa(row.get("min_amount"), interval, currency), to_lpa(row.get("max_amount"), interval, currency)
    exp_min, exp_max = experience_range(get("experience_range") or "")
    posted = get("date_posted")
    remote = row.get("is_remote") is True or "remote" in (get("work_from_home_type") or "").lower()
    return {
        "source": source,
        "source_id": f"{source}:{get('id') or get('job_url')}",
        "url": get("job_url"),
        "title": get("title") or "",
        "company": get("company") or "",
        "location": get("location") or "",
        "posted_at": posted,
        "description": get("description"),
        "employment_type": get("job_type"),
        "industry": get("company_industry"),
        "salary_min_lpa": lo,
        "salary_max_lpa": hi,
        "experience_min": exp_min,
        "experience_max": exp_max,
        "work_mode_hint": "remote" if remote else (get("work_from_home_type") or None),
        "apply_on_company_site": bool(get("job_url_direct")) if source == "indeed" else None,
        "apply_url": get("job_url_direct") or None,
    }


def captcha(errors):
    """True if Naukri answered with its captcha page (it is rate limiting us)."""
    return any("406" in e for e in errors)


class NaukriPages:
    """Naukri job pages (description, industry, company apply link), one at a
    time with a pause between them, through JobSpy's own Naukri session."""

    def __init__(self, delay):
        from jobspy.model import ScraperInput, Site
        from jobspy.naukri import Naukri
        from jobspy.util import TLSRotating, create_session

        self.delay, self.requests, self._last, self._errors = delay, 0, 0.0, 0
        self.scraper = Naukri()
        self.scraper.scraper_input = ScraperInput(site_name=[Site.NAUKRI])
        self.scraper.session = create_session(TLSRotating(None), self.scraper.scraper_input)

    def details(self, job_id):
        """Fields for one job, or None. Raises Blocked on a captcha."""
        from jobspy.model import DescriptionFormat
        from jobspy.naukri.constant import job_page_headers
        from jobspy.naukri.model import JobDetails
        from jobspy.naukri.util import generate_nkparam
        from jobspy.util import description_fields

        time.sleep(max(0.0, self._last + self.delay + random.uniform(0, 2) - time.time()))
        self._last = time.time()
        self.requests += 1
        s = self.scraper
        try:
            r = s.session.get(f"{s.job_page_url}/{job_id}",
                              headers=job_page_headers | {"nkparam": generate_nkparam(job_id)})
        except Exception:
            self._errors += 1
            if self._errors >= 5:                      # e.g. the internet is down: fail the step
                raise RuntimeError("could not reach Naukri job pages (5 tries in a row)")
            return None
        self._errors = 0
        if r.status_code == 406:
            raise Blocked("Naukri asked for a captcha (406)")
        if r.status_code != 200:
            return None
        try:
            job = JobDetails.model_validate(r.json()["jobDetails"])
        except Exception:
            return None
        return {"description": description_fields(job.description, DescriptionFormat.MARKDOWN)["description"],
                "industry": job.industry,
                "apply_url": job.applyRedirectUrl or None}
