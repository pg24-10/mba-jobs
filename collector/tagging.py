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
"""

import json
import re
from datetime import datetime, timezone

from .settings import DATA, config

DIR = DATA / "state" / "tagging"
BATCH = DIR / "batch.json"
TAGGED = DIR / "batch-tagged.json"
FAILED = DIR / "failed.json"                  # job id -> times its tags were refused
GIVE_UP = 2                                   # refused this often: left out of later batches
MODEL = "haiku"

OFF_LEVEL = {"entry", "director", "cxo"}      # too junior or beyond most MBA hires
ASKS_MBA = {"required", "preferred"}
LEVELS = ("required", "preferred", "not mentioned")
COPY_WORDS = 8                                # this many words in a row from the post = copied
THIN_WORDS = 60                               # fewer words of description than this: not tagged, not shown
TO_TAG = {"tagged_at": "is.null", "description_trimmed": "not.is.null", "too_thin": "is.false"}


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


def export(db, limit=50, path=BATCH, log=print):
    """Write the next `limit` jobs to tag. Jobs whose description is too short are
    flagged too_thin on the way and left out."""
    skip = [i for i, n in _failed().items() if n >= GIVE_UP]
    params = {**TO_TAG, "order": "past_isb_recruiter.desc,posted_at.desc.nullslast",
              "select": "id,title,company,location_city,description_trimmed"}
    if skip:
        params["id"] = f"not.in.({','.join(map(str, skip))})"
    rows, flagged = [], 0
    while len(rows) < limit:                      # the database hands out at most 1,000 rows a time
        want = min(1000, limit - len(rows))
        page = db._send("GET", f"{db.base}/jobs", timeout=60, params=params,
                        headers={"Range": f"{len(rows)}-{len(rows) + want - 1}"})
        bad = [r["id"] for r in page if thin(r["description_trimmed"])]
        if bad:                                   # flagged rows drop out, so the next page starts at len(rows)
            mark_thin(db, bad)
            flagged += len(bad)
        rows += [r for r in page if not thin(r["description_trimmed"])]
        if len(page) < want:
            break
    if flagged:
        log(f"left out {flagged} jobs with under {THIN_WORDS} words of description (flagged too_thin)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([{"id": r["id"], "title": r["title"], "company": r["company"],
                                 "city": r["location_city"], "description": r["description_trimmed"]}
                                for r in rows], indent=1, ensure_ascii=False))
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
               masters_mentioned=bool(tag.get("masters_mentioned")), summary=summary,
               duties=duties[:5], looking_for=looking[:5],
               key_skills=[s.strip() for s in tag.get("key_skills") or [] if s and s.strip()][:8],
               fit_score=fit_score(tag, tags))
    for k in ("experience_min", "experience_max"):        # only fill years the job doesn't have
        if job.get(k) is None and _years(tag.get(k)) is not None:
            row[k] = _years(tag[k])
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
    """Save every good tag, delete those jobs' descriptions. Returns (saved, problems)."""
    tags, facts = config("tags"), company_facts()
    jobs = {j["id"]: j for j in json.loads(batch.read_text())}
    have = {r["id"]: r for r in db.select("jobs", {"id": f"in.({','.join(map(str, jobs))})",
                                                    "select": "id,experience_min,experience_max"})} if jobs else {}
    saved, problems, failed = 0, [], _failed()
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
    FAILED.parent.mkdir(parents=True, exist_ok=True)
    FAILED.write_text(json.dumps(failed))
    return saved, problems
