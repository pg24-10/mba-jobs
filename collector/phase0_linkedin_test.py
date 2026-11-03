"""Phase 0: can we read LinkedIn's public guest job pages from this machine?

Runs a small, slow set of guest requests (no login, no cookies) and writes a
report: status codes, results per search, whether OR is respected, whether the
detail page returns a description, and whether a company-jobs search works.

Usage:
    python collector/phase0_linkedin_test.py              # full test (~25 requests)
    python collector/phase0_linkedin_test.py --quick      # 2 requests, parser smoke test
Outputs phase0_report.json and phase0_report.md in the current folder.
"""

import argparse
import html
import json
import random
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
COMPANY_PAGE_URL = "https://www.linkedin.com/company/{slug}"

PAST_24H = "r86400"
PAST_WEEK = "r604800"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

SINGLE_SEARCHES = [
    ("chief of staff", "Bengaluru, Karnataka, India"),
    ("product manager", "Mumbai, Maharashtra, India"),
    ("program manager", "Hyderabad, Telangana, India"),
    ("strategy", "Gurugram, Haryana, India"),
    ("consultant", "Pune, Maharashtra, India"),
    ("brand manager", "Mumbai, Maharashtra, India"),
    ("finance manager", "Chennai, Tamil Nadu, India"),
    ("business analyst", "Bengaluru, Karnataka, India"),
    ("management trainee", "India"),
    ("MBA", "Kolkata, West Bengal, India"),
]

# OR test: two phrases that rarely appear in the same title.
OR_PHRASES = ['"chief of staff"', '"founder\'s office"']
OR_LOCATION = "India"

COMPANY_SLUG = "amazon"

state = {"wait": 2.5, "requests": 0, "blocked": 0}

# python.org builds on macOS ship without a CA bundle; prefer certifi when present.
try:
    import certifi

    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context()


def polite_pause():
    # 2 to 3 seconds plus jitter, never under 1.5 s; doubles after a block.
    time.sleep(max(1.5, state["wait"] + random.uniform(-0.5, 0.8)))


def fetch(url):
    polite_pause()
    state["requests"] += 1
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status, final_url = resp.status, resp.geturl()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        status, final_url = e.code, url
    except Exception as e:  # network error, timeout
        return {"status": None, "error": str(e), "body": "", "final_url": url, "secs": 0}
    if status in (429, 999):
        state["blocked"] += 1
        state["wait"] = min(state["wait"] * 2, 30)
    return {
        "status": status,
        "body": body,
        "final_url": final_url,
        "secs": round(time.time() - started, 2),
        "bytes": len(body),
    }


def clean(text):
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def squash(text):
    return re.sub(r"\s+", " ", clean(text)).strip()


def parse_cards(body):
    """Return a list of {id, title, company, location, posted} from a search page."""
    jobs = []
    for chunk in re.split(r"<li[ >]", body)[1:]:
        m = re.search(r"urn:li:jobPosting:(\d+)", chunk)
        if not m:
            continue

        def grab(cls):
            mm = re.search(r'class="[^"]*' + cls + r'[^"]*"[^>]*>(.*?)</', chunk, re.S)
            return squash(mm.group(1)) if mm else ""

        posted = re.search(r'<time[^>]*datetime="([^"]+)"', chunk)
        company_link = re.search(r'href="https://[a-z]+\.linkedin\.com/company/([^?"/]+)', chunk)
        jobs.append(
            {
                "id": m.group(1),
                "title": grab("base-search-card__title"),
                "company": grab("base-search-card__subtitle") or squash(
                    (re.search(r'hidden-nested-link[^>]*>(.*?)</a>', chunk, re.S) or [None, ""])[1]
                ),
                "company_slug": company_link.group(1) if company_link else "",
                "location": grab("job-search-card__location"),
                "posted": posted.group(1) if posted else "",
            }
        )
    return jobs


def search(keywords, location, tpr=PAST_24H, start=0, extra=None):
    params = {"keywords": keywords, "location": location, "f_TPR": tpr, "start": start}
    params.update(extra or {})
    url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
    r = fetch(url)
    jobs = parse_cards(r["body"]) if r["status"] == 200 else []
    return {
        "keywords": keywords,
        "location": location,
        "f_TPR": tpr,
        "start": start,
        **{k: v for k, v in params.items() if k not in ("keywords", "location", "f_TPR", "start")},
        "status": r["status"],
        "error": r.get("error"),
        "secs": r["secs"],
        "bytes": r.get("bytes", 0),
        "count": len(jobs),
        "jobs": jobs,
    }


def detail(job_id):
    r = fetch(DETAIL_URL.format(job_id=job_id))
    body = r["body"]
    m = re.search(r'class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>', body, re.S)
    desc = squash(m.group(1)) if m else ""
    criteria = re.findall(
        r'description__job-criteria-subheader[^>]*>(.*?)</h3>.*?description__job-criteria-text[^>]*>(.*?)</span>',
        body,
        re.S,
    )
    applicants = re.search(r'num-applicants__caption[^>]*>(.*?)</', body, re.S)
    apply_offsite = "offsite" in body.lower() or "apply-link-offsite" in body
    return {
        "job_id": job_id,
        "status": r["status"],
        "secs": r["secs"],
        "bytes": r.get("bytes", 0),
        "has_description": bool(desc),
        "description_chars": len(desc),
        "description_preview": desc[:300],
        "criteria": {squash(k): squash(v) for k, v in criteria},
        "applicants": squash(applicants.group(1)) if applicants else "",
        "apply_offsite_hint": apply_offsite,
    }


def company_test(slug):
    """Try to find a numeric company id from the public company page, then search jobs by it."""
    r = fetch(COMPANY_PAGE_URL.format(slug=slug))
    body = r["body"]
    ids = set(re.findall(r"f_C=(\d+)", body)) | set(re.findall(r"urn:li:(?:organization|company|fsd_company):(\d+)", body))
    out = {
        "slug": slug,
        "page_status": r["status"],
        "page_final_url": r["final_url"],
        "authwall": "authwall" in r["final_url"] or "authwall" in body[:5000],
        "company_ids_found": sorted(ids),
    }
    if ids:
        cid = sorted(ids, key=lambda x: body.count(x), reverse=True)[0]
        s = search("", "India", tpr=PAST_24H, extra={"f_C": cid})
        out["company_id_used"] = cid
        out["company_search"] = {k: s[k] for k in ("status", "count", "secs")}
        out["company_search_companies"] = sorted({j["company"] for j in s["jobs"]})
        out["company_search_sample"] = [j["title"] for j in s["jobs"][:5]]
    return out


def or_test():
    """Is OR honoured? Compare a grouped OR query against each phrase alone (past week, 2 pages each)."""

    def collect(q):
        rows, statuses = [], []
        for start in (0, 10):
            s = search(q, OR_LOCATION, tpr=PAST_WEEK, start=start)
            statuses.append(s["status"])
            rows += s["jobs"]
        uniq = {j["id"]: j for j in rows}
        return list(uniq.values()), statuses

    group_q = " OR ".join(OR_PHRASES)
    group_jobs, group_status = collect(group_q)
    per_phrase = {}
    for p in OR_PHRASES:
        jobs, st = collect(p)
        per_phrase[p] = {"status": st, "count": len(jobs), "ids": {j["id"] for j in jobs}}

    def matches(title, phrase):
        words = phrase.strip('"').lower().replace("'", "")
        return words in title.lower().replace("'", "").replace("’", "")

    title_hits = {p: sum(matches(j["title"], p) for j in group_jobs) for p in OR_PHRASES}
    neither = [j["title"] for j in group_jobs if not any(matches(j["title"], p) for p in OR_PHRASES)]
    group_ids = {j["id"] for j in group_jobs}
    overlap = {p: len(group_ids & per_phrase[p]["ids"]) for p in OR_PHRASES}
    respected = all(v > 0 for v in title_hits.values()) or all(v > 0 for v in overlap.values())
    return {
        "group_query": group_q,
        "location": OR_LOCATION,
        "window": "past week",
        "group_status": group_status,
        "group_count": len(group_jobs),
        "title_hits_per_phrase": title_hits,
        "overlap_with_single_phrase_results": overlap,
        "single_phrase_counts": {p: v["count"] for p, v in per_phrase.items()},
        "titles_matching_neither": neither[:10],
        "or_respected": respected,
        "group_sample_titles": [j["title"] for j in group_jobs[:12]],
    }


def paging_test(keywords, location):
    """How big is the 'start' step? Fetch start=0,10,20 and check overlap."""
    pages = [search(keywords, location, tpr=PAST_WEEK, start=s) for s in (0, 10, 20)]
    ids = [[j["id"] for j in p["jobs"]] for p in pages]
    return {
        "keywords": keywords,
        "location": location,
        "counts": [p["count"] for p in pages],
        "statuses": [p["status"] for p in pages],
        "overlap_0_10": len(set(ids[0]) & set(ids[1])),
        "overlap_10_20": len(set(ids[1]) & set(ids[2])),
        "unique_total": len(set(sum(ids, []))),
    }


def to_markdown(rep):
    L = ["# Phase 0: LinkedIn guest test", ""]
    L.append(f"Machine: **{rep['machine']}**. Requests made: {rep['requests']}. Blocks (429/999): {rep['blocked']}.")
    L.append("")
    L.append("## Single searches (past 24 hours)")
    L.append("| Keywords | Location | Status | Results | Sample title (company, location) |")
    L.append("|---|---|---|---|---|")
    for s in rep["searches"]:
        j = s["jobs"][0] if s["jobs"] else None
        sample = f"{j['title']} ({j['company']}, {j['location']})" if j else ""
        L.append(f"| {s['keywords']} | {s['location']} | {s['status']} | {s['count']} | {sample} |")
    if "paging" in rep:
        p = rep["paging"]
        L += ["", "## Paging", f"start=0/10/20 gave {p['counts']} results, statuses {p['statuses']}; "
              f"overlap 0-10: {p['overlap_0_10']}, 10-20: {p['overlap_10_20']}; unique {p['unique_total']}."]
    if "or_test" in rep:
        o = rep["or_test"]
        L += ["", "## OR test", f"Query `{o['group_query']}` in {o['location']} ({o['window']}): "
              f"status {o['group_status']}, {o['group_count']} unique results.",
              f"- Titles containing each phrase: {o['title_hits_per_phrase']}",
              f"- Single-phrase result counts: {o['single_phrase_counts']}",
              f"- Overlap with single-phrase results: {o['overlap_with_single_phrase_results']}",
              f"- Titles matching neither (first 10): {o['titles_matching_neither']}",
              f"- **OR respected: {o['or_respected']}**"]
    if "detail" in rep:
        d = rep["detail"]
        L += ["", "## Job detail fetch", f"Job {d['job_id']}: status {d['status']}, description returned: "
              f"**{d['has_description']}** ({d['description_chars']} chars).",
              f"- Criteria: {d['criteria']}", f"- Applicants: {d['applicants']}",
              f"- Preview: {d['description_preview'][:200]}..."]
    if "company" in rep:
        c = rep["company"]
        L += ["", "## Company jobs", "```", json.dumps(c, indent=2), "```"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="2 requests only, to check parsing")
    ap.add_argument("--machine", default="unknown")
    args = ap.parse_args()

    rep = {"machine": args.machine, "searches": []}
    plan = SINGLE_SEARCHES[:1] if args.quick else SINGLE_SEARCHES
    for kw, loc in plan:
        s = search(kw, loc)
        rep["searches"].append(s)
        print(f"[search] {kw!r} @ {loc}: status {s['status']}, {s['count']} results", flush=True)
        if state["blocked"] >= 3:
            print("Too many blocks, stopping early.", flush=True)
            break

    first = next((j for s in rep["searches"] for j in s["jobs"]), None)
    if first:
        rep["detail"] = detail(first["id"])
        print(f"[detail] {first['id']}: status {rep['detail']['status']}, "
              f"description {rep['detail']['description_chars']} chars", flush=True)

    if not args.quick and state["blocked"] < 3:
        rep["paging"] = paging_test("product manager", "Bengaluru, Karnataka, India")
        print(f"[paging] {rep['paging']}", flush=True)
        rep["or_test"] = or_test()
        print(f"[or] respected={rep['or_test']['or_respected']} hits={rep['or_test']['title_hits_per_phrase']}", flush=True)
        rep["company"] = company_test(COMPANY_SLUG)
        print(f"[company] {json.dumps({k: v for k, v in rep['company'].items() if k != 'company_search_sample'})}", flush=True)

    rep["requests"], rep["blocked"] = state["requests"], state["blocked"]
    with open("phase0_report.json", "w") as f:
        json.dump(rep, f, indent=2)
    with open("phase0_report.md", "w") as f:
        f.write(to_markdown(rep))
    print(f"Done. {state['requests']} requests, {state['blocked']} blocks.")
    ok = sum(s["status"] == 200 for s in rep["searches"])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
