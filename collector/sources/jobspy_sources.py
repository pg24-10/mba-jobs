"""Indeed and Naukri through the JobSpy library (public search pages, no login)."""

import logging
import math
import re

from ..settings import config
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
        fetch_description=True,
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
