"""Collect -> normalize -> filter -> dedupe -> ISB tag -> upsert -> inbox -> run log.

Every source runs inside its own try/except: when one fails, the others still
save their jobs and the failure is written to `runs`.
"""

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

from .companies import IsbMatcher
from .settings import INBOX, LOGS, STATE, config, machine
from .sources import ats as ats_source
from .sources import iimjobs as iimjobs_source
from .sources import Blocked, TimeUp, jobspy_sources
from .sources.linkedin import LinkedIn, to_raw as linkedin_raw
from .text import (big_board_title_ok, city_of, company_key, excluded_by, experience_range, fold,
                   is_vague, looks_like_agency, title_key, to_lpa, trim_requirements, work_mode_of)

SITE_CITIES = {l["name"] for l in config("searches")["locations"]}


def now():
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ windows

def _shard_machine(shard):
    """Run-log filter for one split machine, e.g. "github 3/10" -> like.* 3/10."""
    return f"like.* {shard[0]}/{shard[1]}"


def window_start(db, source, default_days=1, shard=None):
    """Catch up from the last successful run of this source (any machine). A split
    machine (shard K/N) also counts its own last finished run ("partial"), so each of
    the N machines catches up on its own searches. Never further back than
    max_window_days (or max_window_days_by_source for this source)."""
    params = {"select": "finished_at", "source": f"eq.{source}", "status": "eq.success",
              "order": "finished_at.desc", "limit": "1"}
    if shard:
        del params["status"]
        params["or"] = f"(status.eq.success,and(status.eq.partial,machine.{_shard_machine(shard)}))"
    rows = db.select("runs", params)
    settings = config("settings")
    days = (settings.get("max_window_days_by_source") or {}).get(source, settings["max_window_days"])
    oldest = now() - timedelta(days=days)
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
    work_mode = work_mode_of(raw.get("work_mode_hint"), location, title)
    if city not in SITE_CITIES:
        if not is_vague(location):            # a real city we do not cover (Kochi, Mysuru)
            return None, f"outside chosen cities: {city}"
        # vague ("Karnataka, India") takes the city we searched in. LinkedIn ignores its
        # remote filter, so a vague job from the remote search counts as remote only
        # when the text says so; otherwise it is kept as India-wide with no city.
        city = raw.get("search_city")
        if city == "Remote (India)" and work_mode != "remote":
            city = None
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
        "applicants": raw.get("applicants"),
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

def collect_linkedin(db, groups, locations, since, log, details=True, flush=None,
                     first_step=0, deadline=None, shard=None):
    """details=False (the backfill): save every job from its search card and queue the
    ones worth opening for Claude to sort (collector/triage.py) instead of opening them.

    Works one step at a time (one search group in one city) and hands each step's jobs
    to `flush` as soon as the step is done, so a block or the time limit never loses
    finished work. Starts at `first_step` and wraps round, so a run that stopped part-way
    is picked up where it left off. On Blocked / TimeUp, `e.next_step` is the step to
    start from next time. Without `flush`, returns all jobs (and e.partial on a block)."""
    li = LinkedIn(log=log)
    li.deadline = deadline
    seconds = (now() - since).total_seconds()
    steps = [(g, loc) for g in groups for loc in locations]
    order = steps_for(steps, first_step, shard)
    if order and order[0] != (shard[0] - 1 if shard else 0):
        log(f"  linkedin: carrying on from step {order[0] + 1} of {len(steps)} (the last run stopped there)")
    out = []
    emit = flush or out.extend
    seen = set()                                          # one job found in two steps: once
    for idx in order:
        g, loc = steps[idx]
        raws = []
        try:
            cards = _linkedin_step(li, g, loc, seconds, log)
            for i in seen & cards.keys():
                del cards[i]
            seen |= cards.keys()
            _linkedin_raws(db, li, cards, details, raws, log, f"{g['id']} / {loc['name']}")
        except Blocked as e:                              # keep the details fetched so far
            emit(raws)
            e.partial, e.next_step = out, idx
            log(f"  linkedin: {li.requests} requests, {li.blocks} push-backs; "
                f"stopped at step {idx + 1} of {len(steps)}")
            if idx == order[0] and not isinstance(e, TimeUp) and len(order) > 1:
                # blocked before finishing even the first step: starting there again
                # tomorrow would jam this machine on one search forever, so move on
                e.next_step = idx + 1
                log(f"  linkedin: step {idx + 1} never finished; the next run starts after it")
            raise
        emit(raws)
    log(f"  linkedin: {li.requests} requests, {li.blocks} push-backs")
    return out


def _linkedin_step(li, g, loc, seconds, log):
    """Search cards for one group in one city, split phrase by phrase past the cap."""
    cards = {}
    extra = loc.get("linkedin_extra") or {}
    places = loc["linkedin"] if isinstance(loc["linkedin"], list) else [loc["linkedin"]]
    n = 0
    for place in places:
        found = _linkedin_search(li, cards, g["query"], place, loc["name"], seconds, extra)
        phrases = jobspy_sources.split_or(g["query"])
        if found >= LINKEDIN_CAP and len(phrases) > 1:
            # LinkedIn stops at 1,000 results (and ignores its filters when logged
            # out), so search each phrase on its own: each gets its own 1,000
            log(f"  linkedin {g['id']} / {place}: hit the 1,000 cap, searching phrase by phrase")
            found = sum(_linkedin_search(li, cards, p, place, loc["name"], seconds, extra)
                        for p in phrases)
        n += found
    log(f"  linkedin {g['id']} / {loc['name']}: {n} cards ({li.requests} requests so far)")
    return cards


def _linkedin_raws(db, li, cards, details, raws, log, label):
    """Turn one step's cards into raw jobs (appended to `raws` as they are made)."""
    # details (description, industry) only for new jobs whose title looks like the
    # searches; the rest are saved from the card alone. Each detail is one request.
    keep = {i: c for i, c in cards.items() if not excluded_by(c["title"])}
    if not keep:
        return
    known = {s.split(":", 1)[1] for s in db.known_source_ids(f"linkedin:{i}" for i in keep)}
    todo = {i for i in keep if i not in known and big_board_title_ok(keep[i]["title"])}
    todo -= {s.split(":", 1)[1] for s in not_worth_opening(db, [linkedin_raw(keep[i]) | {"search_city": keep[i]["search_city"]}
                                                                for i in todo])}
    if not details:
        from . import triage
        triage.queue_cards([keep[i] | {"id": i} for i in sorted(todo)])
        if todo:
            log(f"    {label}: {len(keep) - len(known)} new, {len(todo)} worth opening -> queued for Claude")
        todo = set()
    elif todo:
        log(f"    {label}: {len(keep) - len(known)} new, {len(todo)} worth opening -> fetching details")
    opened = 0
    for i in sorted(keep, key=lambda i: i not in todo):      # the ones to open first
        info = li.detail(i) if i in todo else None
        opened += i in todo
        raw = linkedin_raw(keep[i], info)
        raw["search_city"] = keep[i]["search_city"]
        raws.append(raw)
        if i in todo and opened % 50 == 0:
            log(f"    details: {opened}/{len(todo)}")


LINKEDIN_CAP = 990                  # LinkedIn never returns more than 1,000 per search


def _linkedin_search(li, cards, query, place, city, seconds, extra):
    """One LinkedIn search into `cards`. Returns how many results it gave."""
    n = 0
    for c in li.search(query, place, seconds, extra=extra):
        c["search_city"] = city
        cards.setdefault(c["id"], c)
        n += 1
    return n


def steps_for(steps, first_step=0, shard=None):
    """The step numbers (0-based) to run, starting at `first_step` and wrapping round,
    so a run that stopped part-way is picked up where it left off. shard=(k, n): only
    every n-th step, starting with the k-th (k from 1), for runs split across machines."""
    first = first_step if 0 < first_step < len(steps) else 0
    order = list(range(first, len(steps))) + list(range(first))
    return [i for i in order if not shard or i % shard[1] == shard[0] - 1]


def collect_jobspy(db, source, groups, locations, since, log, flush=None, first_step=0,
                   deadline=None, shard=None):
    """One search (phrase in one city) at a time; each search's jobs go to `flush` as
    soon as it is done, so the time limit or a block never loses finished work. On
    Blocked / TimeUp, `e.next_step` is the search to start from next time."""
    hours = (now() - since).total_seconds() / 3600
    pace = config("settings")["jobspy"]
    delay = pace["delay_seconds"].get(source, 3)
    steps = [(term, loc) for g in groups for term in jobspy_sources.terms_for(source, g["query"])
             for loc in locations]
    order = steps_for(steps, first_step, shard)
    if order and order[0] != (shard[0] - 1 if shard else 0):
        log(f"  {source}: carrying on from search {order[0] + 1} of {len(steps)} (the last run stopped there)")
    out, failing = [], 0
    emit = flush or out.extend
    for idx in order:
        term, loc = steps[idx]
        if deadline and time.time() + 60 >= deadline:
            raise _stop(TimeUp, "time limit for this run reached", idx, out, source, len(steps), log)
        time.sleep(delay)
        found, errors = jobspy_sources.search(source, term, loc[source], hours)
        if source == "naukri" and jobspy_sources.captcha(errors):
            raise _stop(Blocked, "Naukri asked for a captcha (406) on its search page", idx, out, source,
                             len(steps), log)
        if errors:
            log(f"  {source} {term} / {loc['name']}: {len(found)} with errors, "
                f"trying again in {pace['retry_wait_seconds']}s ({errors[-1][:80]})")
            time.sleep(pace["retry_wait_seconds"])
            again, errors = jobspy_sources.search(source, term, loc[source], hours)
            if len(again) >= len(found):
                found = again
        failing = failing + 1 if errors else 0
        for r in found:
            r["search_city"] = loc["name"]
        log(f"  {source} {term} / {loc['name']}: {len(found)}" + (" (incomplete)" if errors else ""))
        if source == "naukri":
            try:
                found = naukri_details(db, found, pace, log, deadline)
            except Blocked as e:                       # keep this search's jobs, stop here
                emit(e.partial)
                e.partial, e.next_step = out, idx + 1
                raise
        emit(found)
        if failing >= pace["give_up_after"]:
            raise RuntimeError(f"{source} kept failing ({failing} searches in a row): {errors[-1][:120]}")
    return out


def _stop(cls, message, idx, out, source, total, log):
    e = cls(message, partial=out)
    e.next_step = idx
    log(f"  {source}: stopped at search {idx + 1} of {total} ({message})")
    return e


class _NoIsb:
    def match(self, company):
        return None


def not_worth_opening(db, raws):
    """source_ids of jobs whose page would add nothing: dropped anyway (e.g. a city we
    do not cover), or the same job (company, title, city) already saved with a
    description from another site."""
    keys, skip = {}, set()
    for r in raws:
        row, _ = normalize(r, _NoIsb())
        if row:
            keys.setdefault(row["dedupe_key"], []).append(r["source_id"])
        else:
            skip.add(r["source_id"])
    for k in db.described_keys(keys) if keys else ():
        skip.update(keys[k])
    return skip


def naukri_details(db, raws, pace, log, deadline=None):
    """Naukri search rows already carry a description, often the whole text. Open
    the job page (one at a time) only for new jobs worth it whose search text is a
    short summary. Every job's key skills are added to its description for tagging."""
    short = pace.get("naukri_short_description_words", 60)
    by_id = {}
    for r in raws:
        by_id.setdefault(r["source_id"], r)
    known = db.known_source_ids(i for i, r in by_id.items() if not excluded_by(r["title"]))
    todo = [i for i, r in by_id.items() if i not in known and big_board_title_ok(r["title"])
            and len((r.get("description") or "").split()) < short]
    skip = not_worth_opening(db, [by_id[i] for i in todo])
    todo = [i for i in todo if i not in skip]
    if todo:
        log(f"    naukri: {len(todo)} new with only a short summary -> opening those")
    pages = jobspy_sources.NaukriPages(pace.get("naukri_page_delay_seconds", 4))
    for n, i in enumerate(todo, 1):
        if deadline and time.time() + 60 >= deadline:     # out of time: the rest keep their summary
            break
        try:
            info = pages.details(i.split("nk-", 1)[-1])
        except Blocked as e:                                 # keep everything; the rest keep their summary
            e.partial = [_with_skills(r) for r in by_id.values()]
            raise
        for field, value in (info or {}).items():
            if field == "description" and len((value or "").split()) > len((by_id[i].get(field) or "").split()):
                by_id[i][field] = value
            else:
                by_id[i][field] = by_id[i].get(field) or value
        if n % 50 == 0:
            log(f"    details: {n}/{len(todo)}")
    return [_with_skills(r) for r in by_id.values()]


def _with_skills(raw):
    skills = raw.pop("skills", None)
    if skills and "Key skills:" not in (raw.get("description") or ""):
        raw["description"] = ((raw.get("description") or "") + f"\n\nKey skills: {skills}").strip()
    return raw


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
                                        "ats_type": "not.in.(none)", "ats_token": "not.is.null"})
    client = ats_source.ATS(log=log)
    raws, refused = [], []
    for c in companies:
        try:
            raws += client.fetch(c["name"], c["ats_type"], c["ats_token"], since)
        except Exception as e:               # one board failing never stops the rest
            log(f"  ats {c['name']}: {e}")
            if "429" in str(e):
                refused.append(c["name"])
    log(f"  ats: {len(companies)} boards, {len(raws)} India jobs in window")
    ATS_REFUSED[:] = [len(companies)] + refused        # for the run summary
    return raws


ATS_REFUSED = []        # [boards read, then the names that still said 429 after retrying]


def learn_boards(db, raws, log, check_sites=True):
    """Apply links tell us where a company posts. Save that for companies we track
    (lineup, ISB, watch list) that have no careers page yet, so later runs read it
    directly:
      - links to Greenhouse / Lever / Ashby / Workday / Oracle are saved as they are
      - links to the company's own site are saved as "site" only if the site lists
        its jobs the Google Jobs way (checked once); otherwise "none" for a month"""
    from .sources.careers_site import CareersSite, careers_host

    boards, sites, client = {}, {}, ats_source.ATS(log=log)
    for raw in raws:
        key = company_key(raw.get("company") or "")
        if not key or not raw.get("apply_url") or key in boards:
            continue
        raw = dict(raw, apply_url=ats_source.resolve_short_link(client.http, raw["apply_url"]))
        ats_type, token = ats_source.board_from_url(raw["apply_url"])
        if ats_type:
            boards.setdefault(key, (ats_type, token, raw["company"]))
        elif careers_host(raw["apply_url"]):
            sites.setdefault(key, (careers_host(raw["apply_url"]), raw["company"]))
    if not boards and not sites:
        return 0
    rows = db.select("companies", {"select": "company_key,ats_type,discovered_at",
                                   "or": "(ats_type.is.null,ats_type.eq.none)"})
    month_ago = (now() - timedelta(days=30)).isoformat()
    learned = 0
    for r in rows:
        key = r["company_key"]
        if key in boards:
            ats_type, token, name = boards[key]
        elif key in sites and check_sites and (r["ats_type"] is None or (r["discovered_at"] or "") < month_ago):
            token, name = sites[key]
            try:
                ats_type = "site" if CareersSite(client, token).check() else "none"
            except Exception as e:
                log(f"  could not check {token}: {e}")
                ats_type = "none"
        else:
            continue
        db.update("companies", {"company_key": key},
                  {"ats_type": ats_type, "ats_token": token, "discovered_at": now().isoformat()})
        if ats_type != "none":
            log(f"  learned careers page: {name} -> {ats_type} / {token}")
            learned += 1
    return learned


# ------------------------------------------------------------------ run

def run(db, sources, groups=None, locations=None, days=None, since=None, isb=None, log=print,
        linkedin_details=True, shard=None):
    """Run the given sources and save the results. Returns a summary dict.

    The window is `since` if given, else the last `days`, else a catch-up from
    each source's last success. shard=(k, n): this machine does every n-th search only
    (a run split across machines); it is logged as "partial" so it never counts as the
    whole window being done, and on a catch-up it carries on from its own last run."""
    searches = config("searches")
    groups = groups or searches["groups"]
    locations = locations or searches["locations"]
    isb = isb or load_isb(db)
    summary, inbox_items = {}, []
    inbox_items += save_unsaved(db, log)

    for source in sources:
        s = summary[source] = {"status": "failed", "found": 0, "kept": 0, "new": 0,
                               "dropped": {}, "error": None}
        run_id = None

        def store(raws, source=source, s=s):
            """Normalize and save a batch of this source's jobs now, so a later
            failure, block or time limit cannot lose them."""
            if source != "ats":
                try:
                    learn_boards(db, raws, log)
                except Exception as e:           # nice to have; never fail the source over it
                    log(f"  could not learn careers pages: {e}")
            rows = []
            for raw in raws:
                row, reason = normalize(raw, isb)
                if row:
                    rows.append(row)
                else:
                    why = reason.split(":")[0]
                    s["dropped"][why] = s["dropped"].get(why, 0) + 1
            merged = merge(rows)
            saved = save(db, merged, source, log)
            by_key = {r["dedupe_key"]: r for r in merged}
            new = [r for r in saved if r["is_new"]]
            inbox_items.extend(inbox_item(by_key[r["dedupe_key"]], r["id"]) for r in new)
            s.update(found=s["found"] + len(raws), kept=s["kept"] + len(rows), new=s["new"] + len(new))

        try:
            catch_up = not since and not days
            start = since or (now() - timedelta(days=days) if days else window_start(db, source, shard=shard))
            run_id = db.insert("runs", {"machine": machine() + (f" {shard[0]}/{shard[1]}" if shard else ""),
                                        "source": source,
                                        "window_start": start.isoformat(),
                                        "linkedin_route": "direct" if source == "linkedin" else None})["run_id"]
            log(f"{source}: since {start:%Y-%m-%d %H:%M} UTC")
            raws = []
            try:
                stepwise = dict(flush=store, deadline=deadline(), shard=shard,
                                first_step=next_step(db, source, shard) if catch_up else 0)
                if source == "linkedin":
                    raws = collect_linkedin(db, groups, locations, start, log, details=linkedin_details,
                                            **stepwise)
                elif source in ("indeed", "naukri"):
                    raws = collect_jobspy(db, source, groups, locations, start, log, **stepwise)
                else:
                    raws = collect(db, source, groups, locations, start, log, linkedin_details)
                s["status"] = "partial" if shard else "success"
                if source == "ats" and len(ATS_REFUSED) > 1:
                    names = ATS_REFUSED[1:]
                    s["error"] = (f"blocked: {len(names)} of {ATS_REFUSED[0]} boards still said 'too many "
                                  f"requests' (429) after retrying: {', '.join(names[:8])}"
                                  + (" ..." if len(names) > 8 else ""))
            except Blocked as e:                 # save what was finished; the rest waits
                raws = e.partial
                stop = getattr(e, "next_step", None)
                why = "reached the time limit" if isinstance(e, TimeUp) else f"blocked: {e}"
                s["status"], s["error"] = "pending", (
                    f"{source} {why}. Left for a later run"
                    + (f" ({NEXT_STEP} {stop + 1})." if stop is not None and catch_up else "."))
                log(f"  {s['error']} Saving the {len(raws)} jobs not saved yet.")
            store(raws)
            log(f"  {source}: {s['found']} found, {s['kept']} kept ({s['new']} new), dropped {s['dropped']}")
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


NEXT_STEP = "carry on from step"


def next_step(db, source, shard=None):
    """Where the last catch-up of this source stopped (0-based), if it stopped part-way.
    shard=(k, n): where this split machine's own last run stopped; whole runs ignore
    split-machine runs."""
    params = {"select": "status,errors", "source": f"eq.{source}", "status": "in.(success,pending)",
              "finished_at": "not.is.null", "order": "finished_at.desc", "limit": "1",
              "machine": "not.like.*/*"}
    if shard:
        params.update(status="in.(partial,pending)", machine=_shard_machine(shard))
    rows = db.select("runs", params)
    if rows and rows[0]["status"] == "pending":
        m = re.search(NEXT_STEP + r" (\d+)", rows[0]["errors"] or "")
        if m:
            return int(m.group(1)) - 1
    return 0


def deadline():
    """time.time() at which collecting must stop, from COLLECT_TIME_LIMIT_MINUTES
    (set on GitHub, which stops a job after a few hours), counted from this run's start."""
    minutes = os.environ.get("COLLECT_TIME_LIMIT_MINUTES")
    return STARTED + float(minutes) * 60 if minutes else None


STARTED = time.time()
UNSAVED = STATE / "unsaved"


def save(db, rows, source, log):
    """Upsert; if Supabase cannot be reached, keep the rows on disk for the next run."""
    if not rows:
        return []
    try:
        return db.upsert_jobs(rows)
    except Exception:
        UNSAVED.mkdir(parents=True, exist_ok=True)
        path = UNSAVED / f"{now():%Y%m%d-%H%M%S}-{source}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, default=str))
        log(f"  could not save {len(rows)} {source} jobs; kept them in {path.name} for the next run")
        raise


def save_unsaved(db, log):
    """Save jobs an earlier run could not. Returns inbox items for the new ones."""
    items = []
    for path in sorted(UNSAVED.glob("*.json")) if UNSAVED.exists() else []:
        try:
            rows = json.loads(path.read_text())
        except FileNotFoundError:             # another backfill window just saved it
            continue
        try:
            saved = db.upsert_jobs(rows)
        except Exception as e:
            log(f"still cannot save {path.name}: {e}")
            break
        by_key = {r["dedupe_key"]: r for r in rows}
        items += [inbox_item(by_key[r["dedupe_key"]], r["id"]) for r in saved if r["is_new"]]
        path.unlink(missing_ok=True)
        log(f"saved {len(rows)} jobs left over from an earlier run ({path.name})")
    return items


def load_isb(db):
    names = [r["name"] for r in db.select("companies", {"select": "name", "in_isb_recruiters": "eq.true"})]
    return IsbMatcher(names)


def collect(db, source, groups, locations, since, log, linkedin_details=True):
    if source == "linkedin":
        return collect_linkedin(db, groups, locations, since, log, details=linkedin_details)
    if source in ("indeed", "naukri"):
        return collect_jobspy(db, source, groups, locations, since, log)
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
    stamp, n = f"{now():%Y-%m-%d-%H%M}", 1
    while True:                               # several steps (or windows) in one minute
        path = INBOX / (f"{stamp}.json" if n == 1 else f"{stamp}-{n}.json")
        try:
            with open(path, "x") as f:
                f.write(json.dumps(items, ensure_ascii=False, indent=1))
            return path
        except FileExistsError:
            n += 1


def write_run_log(summary):
    LOGS.mkdir(parents=True, exist_ok=True)
    with open(LOGS / "runs.jsonl", "a") as f:
        f.write(json.dumps({"at": now().isoformat(), "machine": machine(), **summary}) + "\n")
