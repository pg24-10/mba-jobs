"""Claude's job tags (Phase 3, decided 14 Nov 2026).

Haiku tags jobs in batches of 50 on the Mac:
  tag-export  -> data/state/tagging/batch.json (untagged jobs read straight from Supabase;
                 past ISB recruiters first, then newest)
  Claude      -> data/state/tagging/batch-tagged.json (see .claude/agents/job-tagger.md)
  tag-import  -> checks every tag, works out the fit score, saves it and deletes the
                 job's description (the site keeps only facts and Claude's own words).
With --parts N the export is split into part1.json .. partN.json so N helpers can tag at
once (tested 14 Nov: same usage per job, about 4x faster); tag-import --parts saves every
partK-tagged.json it finds.

The fit score is worked out here, from the tags, so every job gets the same rule.

Saving usage (decided 15 Nov 2026):
- Same company + same title: only one is sent to Claude; the rest get its tags on import
  (dupes.json). A job matching one already tagged gets those tags at export, no Claude.
- The code fills what it can read itself: years of experience, master's mentioned, "MBA not
  mentioned" when the post never names one, and industry / company type for companies in
  config/company_facts.yaml. Claude leaves out the fields listed in a job's already_known.
- Titles that past tags say are almost surely fit 1-2 are not sent at all: they are marked
  tag_skipped (kept, reversible: clear tag_skipped and they come back to the queue).
"""

import json
import math
import re
from datetime import datetime, timezone

from .settings import DATA, config

DIR = DATA / "state" / "tagging"
BATCH = DIR / "batch.json"
TAGGED = DIR / "batch-tagged.json"
FAILED = DIR / "failed.json"                  # job id -> times its tags were refused
DUPES = DIR / "dupes.json"                    # job sent to Claude -> same-title jobs that copy its tags
GIVE_UP = 2                                   # refused this often: left out of later batches
MODEL = "haiku"

OFF_LEVEL = {"entry", "director", "cxo"}      # too junior or beyond most MBA hires
ASKS_MBA = {"required", "preferred"}
LEVELS = ("required", "preferred", "not mentioned")
COPY_WORDS = 8                                # this many words in a row from the post = copied
THIN_WORDS = 60                               # fewer words of description than this: not tagged, not shown
TO_TAG = {"tagged_at": "is.null", "description_trimmed": "not.is.null", "too_thin": "is.false",
          "tag_skipped": "is.null"}
SKIP_ABOVE = 0.99                             # title model this sure of fit 1-2: not sent to Claude
                                              # (cross-checked 15 Nov on 12,330 tags: 94% truly 1-2,
                                              #  about 0.6% of fit 4-5 jobs caught by mistake)
SKIP_REASON = "title: likely fit 1-2"
TAG_COLS = ("function", "seniority", "background_wanted", "mba_requirement", "masters_mentioned", "industry",
            "industry_experience_required", "company_type", "startup_stage", "hands_on", "summary",
            "duties", "looking_for", "key_skills", "fit_score")


def fit_score(tag, tags=None):
    """1-5: start from the function, minus 1 if hands-on, minus 1 if off-level,
    plus 1 if the post asks for an MBA."""
    tags = tags or config("tags")
    score = tags["fit_start"].get(tag.get("function"), 2)
    if tag.get("hands_on"):
        score -= 1
    if tag.get("seniority") in OFF_LEVEL:
        score -= 1
    if tag.get("mba_requirement") in ASKS_MBA:
        score += 1
    return max(1, min(5, score))


def _count(db, params):
    r = db.s.get(f"{db.base}/jobs", params={**params, "select": "id"},
                 headers={"Prefer": "count=exact", "Range": "0-0"}, timeout=60)
    db._check(r)
    return int(r.headers["content-range"].split("/")[1])


def status(db):
    return {"to_tag": _count(db, TO_TAG), "tagged": _count(db, {"tagged_at": "not.is.null"})}


def _failed():
    return {int(k): v for k, v in json.loads(FAILED.read_text()).items()} if FAILED.exists() else {}


def thin(description):
    """True when a post says too little to tag well or to be worth showing."""
    return len((description or "").split()) < THIN_WORDS


def mark_thin(db, ids):
    """Flag these jobs too_thin: never tagged, never shown on the site."""
    for i in range(0, len(ids), 200):
        db._send("PATCH", f"{db.base}/jobs", params={"id": f"in.({','.join(map(str, ids[i:i + 200]))})"},
                 data=json.dumps({"too_thin": True}), timeout=60)


def _same_key(row):
    return _key(row.get("company")), _key(row.get("title"))


def _ids(ids):
    return f"in.({','.join(map(str, ids))})"


def _all(db, params):
    """Every row for these params, 1,000 at a time."""
    rows = []
    while True:
        page = db._send("GET", f"{db.base}/jobs", timeout=60, params=params,
                        headers={"Range": f"{len(rows)}-{len(rows) + 999}"})
        rows += page
        if len(page) < 1000:
            return rows


# ---- title model: is this title almost surely fit 1-2? ----

def _title_words(title):
    w = re.findall(r"[a-z0-9][a-z0-9+#.]*", (title or "").lower())
    return set(w) | {a + "_" + b for a, b in zip(w, w[1:])}


def title_model(rows):
    """Count title words in past tags (rows with title, fit_score)."""
    counts, n = ({}, {}), [0, 0]
    for r in rows:
        y = int(r["fit_score"] < 3)
        n[y] += 1
        for f in _title_words(r["title"]):
            counts[y][f] = counts[y].get(f, 0) + 1
    return counts, n


def p_low(model, title):
    """Chance (0-1) that a job with this title scores fit 1-2."""
    (high, low), (n_high, n_low) = model
    if not n_high or not n_low:
        return 0.0
    s = math.log(n_low / n_high)
    for f in _title_words(title):
        a, b = low.get(f, 0), high.get(f, 0)
        if a + b < 3:                             # words seen fewer than 3 times say nothing
            continue
        s += math.log((a + 0.5) / (n_low + 1)) - math.log((b + 0.5) / (n_high + 1))
    return 1 / (1 + math.exp(-max(-30, min(30, s))))


def mark_skipped(db, ids, reason=SKIP_REASON):
    for i in range(0, len(ids), 200):
        db._send("PATCH", f"{db.base}/jobs", params={"id": _ids(ids[i:i + 200])},
                 data=json.dumps({"tag_skipped": reason}), timeout=60)


# ---- what the code reads from a post itself ----

_NUM = r"(\d{1,2}(?:\.\d)?)"
_YEARS = re.compile(_NUM + r"\s*(?:\+\s*)?(?:(?:-|–|to)\s*" + _NUM + r"\s*\+?\s*)?(?:years?|yrs?)\b", re.I)
_MASTERS = re.compile(r"\bmaster'?s?\b|\bm\.?\s?b\.?\s?a\b|\bpgdm\b|\bpgdba\b|\bpgp\b|\bm\.?\s?tech\b|"
                      r"\bm\.?\s?sc\b|\bm\.?\s?com\b|\bpost[- ]?graduat", re.I)
_MBA = re.compile(r"\bmba\b|\bpgdm\b|\bpgdba\b|\bpgp\b|\bpost[- ]?graduat|business school|b-school|\bmms\b|"
                  r"\bmaster'?s?\b[^.\n]{0,40}\b(?:business|management)\b", re.I)


_MBA_STRICT = re.compile(r"\bmba\b|\bpgdm\b|\bpgdba\b|\bpgp\b|\bmms\b|business school|b-school", re.I)
_MUST = re.compile(r"mandatory|must|required|essential|compulsory|only", re.I)
_SOFT = re.compile(r"prefer|plus|advantage|desirable|added|not mandatory|nice to have|or equivalent|good to have", re.I)


def mba_from_post(text):
    """The code's own read of mba_requirement, used when Claude leaves it out.
    (Required and preferred both add 1 to fit, so the main thing is spotting the mention.)"""
    text = text or ""
    found = [text[max(0, m.start() - 60):m.end() + 60] for m in _MBA_STRICT.finditer(text)]
    if not found:
        return "not mentioned"
    if any(_MUST.search(w) and not _SOFT.search(w) for w in found):
        return "required"
    return "preferred"


def read_years(text):
    """(min, max) years of experience stated in the post, or (None, None).
    Several figures: the largest minimum (the post's overall ask)."""
    text, found = text or "", []
    for m in _YEARS.finditer(text):
        near = (text[max(0, m.start() - 40):m.start()] + text[m.end():m.end() + 60]).lower()
        if "exp" not in near:
            continue
        lo, hi = float(m.group(1)), float(m.group(2)) if m.group(2) else None
        if lo <= 30 and (hi is None or hi <= 40):
            found.append((lo, hi))
    return max(found, key=lambda f: f[0]) if found else (None, None)


def code_fields(text):
    """Fields always filled by the code, never by Claude."""
    lo, hi = read_years(text)
    return {"masters_mentioned": bool(_MASTERS.search(text or "")), "experience_min": lo, "experience_max": hi}


def already_known(job, facts):
    """Fields the code can decide for this job, so Claude leaves them out."""
    known = {}
    if not _MBA.search(job.get("description") or ""):
        known["mba_requirement"] = "not mentioned"
    listed = facts.get(_key(job.get("company")))
    if listed:
        industry, ctype = listed
        known["company_type"] = ctype
        if industry:
            known["industry"] = industry
        if ctype != "startup":
            known["startup_stage"] = None
    return known


# ---- tags copied without Claude ----

def _copy_row(source, own):
    """A tagged job's tags for another job with the same company and title.
    `own` holds the job's own experience_min/max and code_fields."""
    row = {k: source[k] for k in TAG_COLS if k in source}
    row["masters_mentioned"] = own.get("masters_mentioned", row.get("masters_mentioned"))
    if own.get("has_years"):
        row.pop("experience_min", None)
        row.pop("experience_max", None)
    else:
        for k in ("experience_min", "experience_max"):
            if own.get(k) is not None:
                row[k] = own[k]
    return row


def _own(r):
    """What a job keeps of its own when it copies another's tags."""
    have = r.get("experience_min") is not None or r.get("experience_max") is not None
    return {**code_fields(r.get("description_trimmed") or r.get("description")), "has_years": have}


def save_copies(db, pairs, model, now):
    """pairs: [(job id, tag row)]. Saves each with its description deleted."""
    groups = {}
    for jid, row in pairs:
        values = {**row, "tagged_at": now, "tag_model": model, "description_trimmed": None}
        groups.setdefault(json.dumps(values, sort_keys=True), []).append(jid)
    for values, ids in groups.items():
        for i in range(0, len(ids), 200):
            db._send("PATCH", f"{db.base}/jobs", params={"id": _ids(ids[i:i + 200])}, data=values, timeout=60)


def export(db, limit=50, path=BATCH, log=print):
    """Write the next `limit` jobs to tag. On the way:
    - jobs whose description is too short are flagged too_thin;
    - jobs with the same company + title as one already tagged get its tags now;
    - titles almost surely fit 1-2 are marked tag_skipped;
    - of several jobs with the same company + title, only the first is written; the rest
      are listed in dupes.json and get its tags on import."""
    facts = company_facts()
    skip = [i for i, n in _failed().items() if n >= GIVE_UP]
    params = {**TO_TAG, "order": "past_isb_recruiter.desc,posted_at.desc.nullslast",
              "select": "id,title,company,location_city,description_trimmed,experience_min,experience_max"}
    if skip:
        params["id"] = f"not.in.({','.join(map(str, skip))})"

    done = _all(db, {"tagged_at": "not.is.null", "too_thin": "is.false", "tag_model": "eq." + MODEL,
                     "select": "id,company,title,fit_score"})
    tagged_as = {_same_key(r): r["id"] for r in done}
    model = title_model(done)

    rows, dupes, reps, offset = [], {}, {}, 0
    n_thin = n_skip = n_dupe = 0
    reuse = []                                    # (job row, id of the tagged job to copy)
    while len(rows) < limit:                      # the database hands out at most 1,000 rows a time
        page = db._send("GET", f"{db.base}/jobs", timeout=60, params=params,
                        headers={"Range": f"{offset}-{offset + 999}"})
        thin_ids, skip_ids = [], []
        for r in page:
            if len(rows) >= limit:
                break
            key = _same_key(r)
            if thin(r["description_trimmed"]):
                thin_ids.append(r["id"])
            elif key in tagged_as:
                reuse.append((r, tagged_as[key]))
            elif key in reps:
                dupes.setdefault(reps[key], []).append({"id": r["id"], **_own(r)})
                n_dupe += 1
            elif p_low(model, r["title"]) >= SKIP_ABOVE:
                skip_ids.append(r["id"])
            else:
                reps[key] = r["id"]
                rows.append(r)
        # flagged, skipped and copied rows drop out of the queue; the rest stay in it
        offset += len(page) - len(thin_ids) - len(skip_ids)
        if thin_ids:
            mark_thin(db, thin_ids)
            n_thin += len(thin_ids)
        if skip_ids:
            mark_skipped(db, skip_ids)
            n_skip += len(skip_ids)
        if len(page) < 1000:
            break
    if reuse:                                     # copied rows leave the queue too, but only now
        want, src = sorted({s for _, s in reuse}), {}
        for i in range(0, len(want), 200):
            src.update({r["id"]: r for r in _all(db, {"id": _ids(want[i:i + 200]),
                                                      "select": "id," + ",".join(TAG_COLS)})})
        save_copies(db, [(r["id"], _copy_row(src[s], _own(r))) for r, s in reuse if s in src],
                    MODEL + "-copy", datetime.now(timezone.utc).isoformat())
    if n_thin:
        log(f"left out {n_thin} jobs with under {THIN_WORDS} words of description (flagged too_thin)")
    if n_skip:
        log(f"skipped {n_skip} jobs whose title is almost surely fit 1-2 (marked tag_skipped)")
    if reuse:
        log(f"gave {len(reuse)} jobs the tags of an already-tagged job with the same company and title")
    if n_dupe:
        log(f"{n_dupe} more jobs share a company and title with a job in this batch; they get its tags on import")

    path.parent.mkdir(parents=True, exist_ok=True)
    out = []
    for r in rows:
        job = {"id": r["id"], "title": r["title"], "company": r["company"], "city": r["location_city"],
               "description": r["description_trimmed"]}
        known = already_known(job, facts)
        if known:
            job["already_known"] = known
        out.append(job)
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    DUPES.write_text(json.dumps(dupes))
    return len(rows)


def _part(i, tagged=False):
    return DIR / f"part{i}{'-tagged' if tagged else ''}.json"


def _old_parts():
    return sorted(DIR.glob("part*.json"))


def export_parts(db, parts, size=50):
    """Write the next parts*size jobs as part1.json .. partN.json. Returns the jobs per part.
    Refuses while earlier parts are still waiting to be imported."""
    if _old_parts():
        raise RuntimeError("earlier part files are still there; run tag-import --parts first")
    n = export(db, parts * size, DIR / "all.json")
    jobs = json.loads((DIR / "all.json").read_text())
    counts = []
    for i in range(parts):
        chunk = jobs[i * size:(i + 1) * size]
        if chunk:
            _part(i + 1).write_text(json.dumps(chunk, indent=1, ensure_ascii=False))
            counts.append(len(chunk))
    (DIR / "all.json").unlink()
    return counts


def import_parts(db, log=print):
    """Import every partK-tagged.json, then remove that part's files. Parts with no tags
    yet are left for a later run. Returns (saved, problems, parts left)."""
    saved, problems, left = 0, [], 0
    for batch in sorted(DIR.glob("part*.json")):
        if batch.stem.endswith("-tagged"):
            continue
        out = batch.with_name(batch.stem + "-tagged.json")
        if not out.exists():
            left += 1
            continue
        try:
            n, p = import_tags(db, out, batch)
        except json.JSONDecodeError:
            problems.append(f"{out.name}: not valid JSON, part left as it is")
            left += 1
            continue
        saved += n
        problems += p
        batch.unlink()
        out.unlink()
    return saved, problems, left


def _words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def copied(own_words, post):
    """True if any line of Claude's text repeats COPY_WORDS words in a row from the post."""
    w = _words(post)
    runs = {tuple(w[i:i + COPY_WORDS]) for i in range(len(w) - COPY_WORDS + 1)}
    for line in own_words:
        x = _words(line)
        if any(tuple(x[i:i + COPY_WORDS]) in runs for i in range(len(x) - COPY_WORDS + 1)):
            return True
    return False


def _years(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def check(tag, job, tags):
    """The row to save for one tag, or the reason it can't be saved."""
    tag = {**tag, **(job.get("already_known") or {})}  # what the code decided wins
    if tag.get("mba_requirement") is None:                  # left out by mistake: the code reads it
        tag["mba_requirement"] = mba_from_post(job.get("description"))
    for field in ("function", "seniority", "industry", "company_type"):
        if tag.get(field) not in tags[field]:
            return f"{field} {tag.get(field)!r} is not in tags.yaml"
    for field in ("mba_requirement", "industry_experience_required"):
        if tag.get(field) not in LEVELS:
            return f"{field} {tag.get(field)!r}"
    bg = tag.get("background_wanted") or []
    if not bg or any(b not in tags["background_wanted"] for b in bg):
        return f"background_wanted {bg!r}"
    stage = tag.get("startup_stage")
    if stage is not None and stage not in tags["startup_stage"]:
        return f"startup_stage {stage!r}"
    if not isinstance(tag.get("hands_on"), bool):
        return "hands_on must be true or false"
    summary = (tag.get("summary") or "").strip()
    duties = [d.strip() for d in tag.get("duties") or [] if d and d.strip()]
    looking = [d.strip() for d in tag.get("looking_for") or [] if d and d.strip()]
    if not summary or len(duties) < 2 or not looking:
        return "summary, duties or looking_for is empty"
    if copied([summary, *duties, *looking], job["description"]):
        return "copied words from the post"
    row = {k: tag[k] for k in ("function", "seniority", "mba_requirement", "industry",
                               "industry_experience_required", "company_type", "hands_on")}
    row.update(background_wanted=bg[:3], startup_stage=stage if tag["company_type"] == "startup" else None,
               summary=summary,
               duties=duties[:5], looking_for=looking[:5],
               key_skills=[s.strip() for s in tag.get("key_skills") or [] if s and s.strip()][:8],
               fit_score=fit_score(tag, tags))
    own = code_fields(job.get("description"))
    row["masters_mentioned"] = own["masters_mentioned"]
    if job.get("experience_min") is None and job.get("experience_max") is None:
        for k in ("experience_min", "experience_max"):  # only fill years the job doesn't have
            if own[k] is not None:
                row[k] = own[k]
    return row


def _key(name):
    """Company name for matching: case, punctuation and spacing ignored."""
    return " ".join(re.findall(r"[a-z0-9]+", (name or "").lower().replace("&", " and ")))


def company_facts():
    """{matching key: (industry or None, company_type)} from config/company_facts.yaml."""
    return {_key(name): tuple(v) for name, v in (config("company_facts") or {}).items()}


def fix_company(row, company, facts):
    """Put the listed industry / company type on a tag row. Returns the fields changed."""
    known = facts.get(_key(company))
    if not known:
        return {}
    industry, ctype = known
    want = {"company_type": ctype}
    if industry:
        want["industry"] = industry
    if ctype != "startup":
        want["startup_stage"] = None
    changed = {k: v for k, v in want.items() if row.get(k) != v}
    row.update(changed)
    return changed


def apply_companies(db, log=print):
    """Bring jobs already tagged in line with the company list. Returns jobs changed."""
    facts, rows = company_facts(), []
    while True:
        page = db._send("GET", f"{db.base}/jobs", timeout=60,
                        params={"tagged_at": "not.is.null", "order": "id",
                                "select": "id,company,industry,company_type,startup_stage"},
                        headers={"Range": f"{len(rows)}-{len(rows) + 999}"})
        rows += page
        if len(page) < 1000:
            break
    groups = {}
    for r in rows:
        changed = fix_company(dict(r), r["company"], facts)
        if changed:
            groups.setdefault(json.dumps(changed, sort_keys=True), []).append(r["id"])
    for values, ids in groups.items():
        for i in range(0, len(ids), 200):
            db._send("PATCH", f"{db.base}/jobs", params={"id": f"in.({','.join(map(str, ids[i:i + 200]))})"},
                     data=values, timeout=60)
    n = sum(len(ids) for ids in groups.values())
    log(f"checked {len(rows)} tagged jobs against {len(facts)} listed companies; corrected {n}")
    return n


def import_tags(db, path=TAGGED, batch=BATCH, log=print):
    """Save every good tag, delete those jobs' descriptions, and give the same tags to the
    same-title jobs listed in dupes.json. Returns (saved, problems)."""
    tags, facts = config("tags"), company_facts()
    jobs = {j["id"]: j for j in json.loads(batch.read_text())}
    have = {r["id"]: r for r in db.select("jobs", {"id": f"in.({','.join(map(str, jobs))})",
                                                    "select": "id,experience_min,experience_max"})} if jobs else {}
    saved, problems, failed = 0, [], _failed()
    dupes = json.loads(DUPES.read_text()) if DUPES.exists() else {}
    copies = []
    now = datetime.now(timezone.utc).isoformat()
    for tag in json.loads(path.read_text()):
        job = jobs.get(tag.get("id"))
        if job is None:
            problems.append(f"{tag.get('id')}: not in this batch")
            continue
        row = check(tag, {**job, **have.get(job["id"], {})}, tags)
        if isinstance(row, str):
            problems.append(f"{job['id']} {job['title'][:40]}: {row}")
            failed[job["id"]] = failed.get(job["id"], 0) + 1
            continue
        fix_company(row, job.get("company"), facts)
        db.update("jobs", {"id": job["id"]}, {**row, "tagged_at": now, "tag_model": MODEL,
                                              "description_trimmed": None})
        saved += 1
        copies += [(d["id"], _copy_row(row, d)) for d in dupes.pop(str(job["id"]), [])]
    if copies:
        save_copies(db, copies, MODEL + "-copy", now)
        log(f"gave {len(copies)} same-title jobs the tags of the job tagged for them")
    DUPES.write_text(json.dumps(dupes))
    FAILED.parent.mkdir(parents=True, exist_ok=True)
    FAILED.write_text(json.dumps(failed))
    return saved, problems
