"""Collect -> normalize -> filter -> dedupe -> ISB tag -> upsert -> inbox -> run log.

Every source runs inside its own try/except: when one fails, the others still
save their jobs and the failure is written to `runs`.
"""

import json
import re
from datetime import datetime, timedelta, timezone

from .companies import IsbMatcher
from .settings import INBOX, LOGS, config, machine
from .sources import ats as ats_source
from .sources import iimjobs as iimjobs_source
from .sources import jobspy_sources
from .sources.linkedin import Blocked, LinkedIn, to_raw as linkedin_raw
from .text import (city_of, company_key, excluded_by, experience_range, fold,
                   looks_like_agency, title_key, to_lpa, trim_requirements, work_mode_of)

SITE_CITIES = {l["name"] for l in config("searches")["locations"]}


def now():
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ windows

def window_start(db, source, default_days=1):
    """Catch up from the last successful run of this source (any machine)."""
    rows = db.select("runs", {"select": "finished_at", "source": f"eq.{source}",
                              "status": "eq.success", "order": "finished_at.desc", "limit": "1"})
    oldest = now() - timedelta(days=config("settings")["max_window_days"])
    if not rows or not rows[0]["finished_at"]:
        return max(oldest, now() - timedelta(days=default_days))
    last = datetime.fromisoformat(rows[0]["finished_at"])
    return max(oldest, last - timedelta(hours=2))          # small overlap, dedupe absorbs it


# ------------------------------------------------------------------ normalize

_MONEY = re.compile(r"₹\s?([\d,]+(?:\.\d+)?)\s*/?\s*(yr|year|mo|month|hr|hour)?", re.I)


def salary_from_text(text):
    """LinkedIn '₹15,00,000.00/yr - ₹25,00,000.00/yr' -> (15.0, 25.0)."""
    found = _MONEY.findall(text or "")
    if not found:
        return None, None
    unit = {"mo": "monthly", "month": "monthly", "hr": "hourly", "hour": "hourly"}
    vals = [to_lpa(a.replace(",", ""), unit.get((u or "yr").lower(), "yearly")) for a, u in found]
    vals = [v for v in vals if v]
    return (min(vals), max(vals)) if vals else (None, None)


def normalize(raw, isb):
    """Raw job from any source -> a `jobs` row, or (None, reason) when dropped."""
    title, company = (raw.get("title") or "").strip(), (raw.get("company") or "").strip()
    if not title or not company:
        return None, "missing title or company"
    hit = excluded_by(title)
    if hit:
        return None, f"title: {hit}"
    if fold(raw.get("employment_type") or "") in ("internship", "intern"):
        return None, "employment type: internship"

    location = raw.get("location") or ""
    city = city_of(location)
    # vague locations ("KA, India", "India") take the city we searched in
    if city not in SITE_CITIES and raw.get("search_city"):
        city = raw["search_city"]
    work_mode = work_mode_of(raw.get("work_mode_hint"), location, title)
    if city == "Remote (India)":
        work_mode = "remote"

    lo, hi = raw.get("salary_min_lpa"), raw.get("salary_max_lpa")
    if lo is None and hi is None and raw.get("salary_text"):
        lo, hi = salary_from_text(raw["salary_text"])
    exp_min, exp_max = raw.get("experience_min"), raw.get("experience_max")
    if exp_min is None and exp_max is None:
        exp_min, exp_max = experience_range(raw.get("description"))

    key = company_key(company)
    show_isb = config("settings").get("show_past_isb_recruiter", True)
    return {
        "dedupe_key": f"{key}|{title_key(title)}|{fold(city or '')}",
        "title": title,
        "company": company,
        "company_key": key,
        "location_city": city,
        "location_raw": location or None,
        "work_mode": work_mode,
        "source_links": [raw["url"]] if raw.get("url") else [],
        "sources": [raw["source"]],
        "source_ids": [raw["source_id"]],
        "posted_at": raw.get("posted_at"),
        "experience_min": exp_min,
        "experience_max": exp_max,
        "salary_min_lpa": lo,
        "salary_max_lpa": hi,
        "salary_shown": lo is not None or hi is not None,
        "employment_type": raw.get("employment_type"),
        "is_agency": looks_like_agency(company, raw.get("industry") or ""),
        "apply_on_company_site": raw.get("apply_on_company_site"),
        "past_isb_recruiter": bool(show_isb and isb.match(company)),
        "description_trimmed": trim_requirements(raw.get("description")),
    }, None


def merge(rows):
    """Collapse rows with the same dedupe_key, keeping every link and source."""
    out = {}
    for r in rows:
        k = r["dedupe_key"]
        if k not in out:
            out[k] = dict(r)
            continue
        m = out[k]
        for f in ("source_links", "sources", "source_ids"):
            m[f] = list(dict.fromkeys(m[f] + r[f]))
        dates = [d for d in (m["posted_at"], r["posted_at"]) if d]
        m["posted_at"] = min(dates) if dates else None
        for f, v in r.items():
            if m.get(f) is None and v is not None:
                m[f] = v
        m["salary_shown"] = m["salary_shown"] or r["salary_shown"]
        m["is_agency"] = m["is_agency"] or r["is_agency"]
    return list(out.values())


# ------------------------------------------------------------------ sources

def collect_linkedin(db, groups, locations, since, log):
    li = LinkedIn(log=log)
    seconds = (now() - since).total_seconds()
    cards = {}
    for g in groups:
        for loc in locations:
            n = 0
            for c in li.search(g["query"], loc["linkedin"], seconds, extra=loc.get("linkedin_extra")):
                c["search_city"] = loc["name"]
                cards.setdefault(c["id"], c)
                n += 1
            log(f"  linkedin {g['id']} / {loc['name']}: {n} cards ({li.requests} requests so far)")
    # details (description, industry) only for kept jobs we have not stored before
    keep = {i: c for i, c in cards.items() if not excluded_by(c["title"])}
    known = {s.split(":", 1)[1] for s in db.known_source_ids(f"linkedin:{i}" for i in keep)}
    raws = []
    todo = [i for i in keep if i not in known]
    log(f"  linkedin: {len(cards)} cards, {len(keep)} after title filter, {len(todo)} new -> fetching details")
    for n, i in enumerate(keep, 1):
        info = li.detail(i) if i in todo else None
        raw = linkedin_raw(keep[i], info)
        raw["search_city"] = keep[i]["search_city"]
        raws.append(raw)
        if i in todo and n % 50 == 0:
            log(f"    details: {n}/{len(keep)}")
    log(f"  linkedin: {li.requests} requests, {li.blocks} push-backs")
    return raws


def collect_jobspy(source, groups, locations, since, log):
    hours = (now() - since).total_seconds() / 3600
    raws = []
    for g in groups:
        for term in jobspy_sources.terms_for(source, g["query"]):
            for loc in locations:
                found = jobspy_sources.search(source, term, loc[source], hours)
                for r in found:
                    r["search_city"] = loc["name"]
                raws += found
                log(f"  {source} {term} / {loc['name']}: {len(found)}")
    return raws


def collect_iimjobs(groups, locations, since, log):
    """IIMjobs searches all of India; keep jobs in the cities being collected."""
    client = iimjobs_source.IIMJobs(log=log)
    wanted = {l["name"] for l in locations}
    raws, seen = [], set()
    for g in groups:
        for term in jobspy_sources.split_or(g["query"]):
            found = client.search(term, since)
            kept = 0
            for job in found:
                raw = iimjobs_source.to_raw(job)
                cities = [c for c in map(city_of, raw["locations"]) if c in wanted]
                if not cities or raw["source_id"] in seen:
                    continue
                seen.add(raw["source_id"])
                raw["search_city"] = cities[0]
                raws.append(raw)
                kept += 1
            log(f"  iimjobs {term}: {len(found)} found, {kept} in chosen cities")
    log(f"  iimjobs: {client.requests} requests")
    return raws


def collect_ats(db, since, log):
    companies = db.select("companies", {"select": "name,ats_type,ats_token",
                                        "ats_type": "not.is.null", "ats_token": "not.is.null"})
    client = ats_source.ATS(log=log)
    raws = []
    for c in companies:
        try:
            raws += client.fetch(c["name"], c["ats_type"], c["ats_token"], since)
        except Exception as e:               # one board failing never stops the rest
            log(f"  ats {c['name']}: {e}")
    log(f"  ats: {len(companies)} boards, {len(raws)} India jobs in window")
    return raws


# ------------------------------------------------------------------ run

def run(db, sources, groups=None, locations=None, days=None, log=print):
    """Run the given sources and save the results. Returns a summary dict."""
    searches = config("searches")
    groups = groups or searches["groups"]
    locations = locations or searches["locations"]
    names = [r["name"] for r in db.select("companies", {"select": "name", "in_isb_recruiters": "eq.true"})]
    isb = IsbMatcher(names)
    summary, inbox_items = {}, []

    for source in sources:
        s = summary[source] = {"status": "failed", "found": 0, "kept": 0, "new": 0,
                               "dropped": {}, "error": None}
        run_id = None
        try:
            since = now() - timedelta(days=days) if days else window_start(db, source)
            run_id = db.insert("runs", {"machine": machine(), "source": source,
                                        "window_start": since.isoformat(),
                                        "linkedin_route": "direct" if source == "linkedin" else None})["run_id"]
            log(f"{source}: since {since:%Y-%m-%d %H:%M} UTC")
            raws = []
            try:
                raws = collect(db, source, groups, locations, since, log)
                s["status"] = "success"
            except Blocked as e:
                s["status"], s["error"] = "pending", f"LinkedIn blocked: {e}. Left for the Mac."
                log(f"  {s['error']}")

            rows = []
            for raw in raws:
                row, reason = normalize(raw, isb)
                if row:
                    rows.append(row)
                else:
                    why = reason.split(":")[0]
                    s["dropped"][why] = s["dropped"].get(why, 0) + 1
            # save this source now, so a later failure cannot lose it
            merged = merge(rows)
            saved = db.upsert_jobs(merged) if merged else []
            by_key = {r["dedupe_key"]: r for r in merged}
            new = [r for r in saved if r["is_new"]]
            inbox_items += [inbox_item(by_key[r["dedupe_key"]], r["id"]) for r in new]
            s.update(found=len(raws), kept=len(rows), new=len(new))
            log(f"  {source}: {len(raws)} found, {len(rows)} kept ({len(new)} new), dropped {s['dropped']}")
        except Exception as e:
            s["status"], s["error"] = "failed", f"{type(e).__name__}: {e}"
            log(f"  {source} FAILED: {s['error']}")
        finally:
            if run_id:
                try:
                    db.update("runs", {"run_id": run_id},
                              {"finished_at": now().isoformat(), "jobs_found": s["found"],
                               "jobs_new": s["new"], "status": s["status"], "errors": s["error"]})
                except Exception as e:
                    log(f"  could not write the {source} run log: {e}")

    inbox = write_inbox(inbox_items)
    try:
        stale = db.rpc("mark_stale")
    except Exception as e:
        stale = f"? ({e})"
    review = isb.write_review_log()
    log(f"done: {sum(s['new'] for s in summary.values())} new jobs, {stale} marked stale"
        + (f", inbox {inbox.name}" if inbox else "") + (f", ISB review list {review}" if review else ""))
    write_run_log(summary)
    return summary


def collect(db, source, groups, locations, since, log):
    if source == "linkedin":
        return collect_linkedin(db, groups, locations, since, log)
    if source in ("indeed", "naukri"):
        return collect_jobspy(source, groups, locations, since, log)
    if source == "iimjobs":
        return collect_iimjobs(groups, locations, since, log)
    if source == "ats":
        return collect_ats(db, since, log)
    raise ValueError(f"unknown source {source}")


def inbox_item(job, job_id):
    return {"id": job_id, "title": job["title"], "company": job["company"],
            "location": job["location_city"], "experience_min": job["experience_min"],
            "experience_max": job["experience_max"], "description": job["description_trimmed"]}


def write_inbox(items):
    """New untagged jobs for Claude, as data/inbox/YYYY-MM-DD-HHMM.json."""
    if not items:
        return None
    INBOX.mkdir(parents=True, exist_ok=True)
    path = INBOX / f"{now():%Y-%m-%d-%H%M}.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1))
    return path


def write_run_log(summary):
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "runs.jsonl", "a") as f:
        f.write(json.dumps({"at": now().isoformat(), "machine": machine(), **summary}) + "\n")
