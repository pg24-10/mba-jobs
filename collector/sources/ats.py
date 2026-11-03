"""Company career pages on Greenhouse, Lever, Ashby, Workday and Oracle (the public
JSON their own careers pages load; no login, no keys).

Each company in `companies` with ats_type + ats_token is fetched once per run;
only India (or remote-India) jobs inside the window are kept. Tokens:
  greenhouse / lever / ashby   board name, e.g. "okta"
  workday                      "<tenant>.<wdN>|<site>", e.g. "diageo.wd3|Diageo_Careers"
  oracle                       "<host>|<site number>", e.g. "eofh.fa.em2.oraclecloud.com|CX_3001"
  site                         the careers site's host (see careers_site.py)
  none                         checked: no page we can read (tried again after a month)

Workday and Oracle boards can hold thousands of jobs (Tata Capital lists 5,000+
loan officer roles), so only titles that look like the searches are opened
for details (see `big_board_title_words` in filters.yaml).
"""

import html
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlparse

import requests

from ..settings import config
from ..text import big_board_title_ok, city_of, fold, is_vague

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


def board_from_url(url):
    """Apply link -> (ats_type, token), or (None, None) for any other site.
    'https://diageo.wd3.myworkdayjobs.com/en-US/Diageo_Careers/job/...' -> ('workday', 'diageo.wd3|Diageo_Careers')"""
    if not url:
        return None, None
    u = urlparse(url)
    host = (u.hostname or "").lower()
    parts = [p for p in u.path.split("/") if p]
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        token = (parse_qs(u.query).get("for") or [None])[0] if parts[:1] == ["embed"] else (parts or [None])[0]
        return ("greenhouse", token) if token else (None, None)
    if host == "jobs.lever.co" and parts:
        return "lever", parts[0]
    if host == "jobs.ashbyhq.com" and parts:
        return "ashby", unquote(parts[0])
    m = re.fullmatch(r"([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com", host)
    if m and parts:
        site = parts[1] if re.fullmatch(r"[a-z]{2}(-[A-Za-z]{2})?", parts[0]) and len(parts) > 1 else parts[0]
        if site not in ("job", "wday"):
            return "workday", f"{m.group(1)}.{m.group(2)}|{site}"
    m = re.fullmatch(r"(wd\d+)\.myworkdaysite\.com", host)       # .../recruiting/<tenant>/<site>/job/...
    if m and "recruiting" in parts and parts.index("recruiting") + 2 < len(parts):
        i = parts.index("recruiting")
        return "workday", f"{parts[i + 1]}.{m.group(1)}|{parts[i + 2]}"
    if host.endswith(".oraclecloud.com") and "sites" in parts:
        i = parts.index("sites")
        if i + 1 < len(parts):
            return "oracle", f"{host}|{parts[i + 1]}"
    return None, None


SHORT_LINKS = ("grnh.se",)          # Greenhouse's short links: follow once to the real board


def resolve_short_link(http, url):
    """Follow a known short link to where it points (one request), else return it unchanged."""
    if (urlparse(url or "").hostname or "").lower() not in SHORT_LINKS:
        return url
    try:
        return http.head(url, allow_redirects=True, timeout=20).url
    except requests.RequestException:
        return url


def _workday_age(posted_on):
    """'Posted Today' / 'Posted Yesterday' / 'Posted 4 Days Ago' / 'Posted 30+ Days Ago' -> days."""
    text = (posted_on or "").lower()
    if "today" in text:
        return 0
    if "yesterday" in text:
        return 1
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) + (1 if "+" in text else 0) if m else None


def _site_city(locations, title=""):
    """The site city a big-board job is in, or None. Checked before opening a job, so a
    board's 200 branch roles in Jaipur cost nothing. When the location only says
    "India", the title often names the branch ("Sales Manager - Hosur - JM")."""
    cities = {l["name"] for l in config("searches")["locations"]}
    for l in filter(None, locations):
        if city_of(l) in cities:
            return city_of(l)
    if any(is_vague(l) for l in locations if l) and city_of(title) in cities:
        return city_of(title)
    return None


def _plain(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def _when(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):          # Lever: milliseconds
        return datetime.fromtimestamp(value / 1000, timezone.utc)
    try:
        when = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)   # Workday / Oracle send plain dates


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

    def _text(self, url):
        """A page as text, or None if it is missing or refuses us (for careers sites)."""
        time.sleep(max(0.0, self._last + self.delay - time.time()))
        self._last = time.time()
        try:
            r = self.http.get(url, timeout=30)
        except requests.RequestException:
            return None
        return r.text if r.ok else None

    def _post(self, url, body):
        time.sleep(max(0.0, self._last + self.delay - time.time()))
        self._last = time.time()
        r = self.http.post(url, json=body, timeout=30)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def fetch(self, company, ats_type, token, since):
        """India jobs for one company posted/updated since `since` (aware datetime)."""
        if ats_type == "workday":
            found = self._workday(token, since)
        elif ats_type == "oracle":
            found = self._oracle(token, since)
        elif ats_type == "site":
            from .careers_site import CareersSite
            found = CareersSite(self, token).jobs(since)
        else:
            data = self._get(URLS[ats_type].format(token=token))
            if data is None:
                return []
            found = self._parse(ats_type, data)
        jobs = []
        for j in found:
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

    # ------------------------------------------------------------ Workday / Oracle

    def _big_board_pages(self):
        return int(config("settings")["ats"].get("max_pages_big_boards", 25))

    def _workday(self, token, since):
        tenant_wd, site = token.split("|", 1)
        host = f"https://{tenant_wd}.myworkdayjobs.com"
        api = f"{host}/wday/cxs/{tenant_wd.split('.')[0]}/{site}"
        max_age = (datetime.now(timezone.utc) - since).days + 1 if since else None
        for page in range(self._big_board_pages()):
            data = self._post(f"{api}/jobs", {"limit": 20, "offset": page * 20,
                                              "searchText": "India", "appliedFacets": {}})
            postings = (data or {}).get("jobPostings") or []
            for p in postings:
                age = _workday_age(p.get("postedOn"))
                where = p.get("locationsText") or ""
                if (max_age is not None and age is not None and age > max_age) \
                        or not (in_india(where) or "location" in where.lower()) \
                        or not ("location" in where.lower() or _site_city([where], p.get("title"))) \
                        or not big_board_title_ok(p.get("title")):
                    continue
                info = ((self._get(api + p["externalPath"]) or {}).get("jobPostingInfo")) or {}
                locs = [info.get("location") or where] + list(info.get("additionalLocations") or [])
                city = _site_city(locs, p.get("title"))
                if not city:                          # "2 Locations" turned out to be elsewhere
                    continue
                if not any(city_of(l) == city for l in locs):
                    locs.insert(0, f"{city}, India")
                yield {"_id": info.get("jobReqId") or p["externalPath"].rsplit("_", 1)[-1],
                       "_when": info.get("startDate") or (datetime.now(timezone.utc) - timedelta(days=age or 0)).date().isoformat(),
                       "title": info.get("title") or p.get("title", ""),
                       "url": info.get("externalUrl") or f"{host}/en-US/{site}{p['externalPath']}",
                       "location": " / ".join(l for l in locs if l),
                       "employment_type": info.get("timeType"),
                       "description": _plain(info.get("jobDescription"))}
            if len(postings) < 20 or (page + 1) * 20 >= (data or {}).get("total", 0):
                break

    def _oracle(self, token, since):
        host, site = token.split("|", 1)
        api = f"https://{host}/hcmRestApi/resources/latest"
        for page in range(self._big_board_pages()):
            data = self._get(f"{api}/recruitingCEJobRequisitions?onlyData=true"
                             f"&expand=requisitionList.secondaryLocations&finder=findReqs;"
                             f"siteNumber={site},limit=25,offset={page * 25},sortBy=POSTING_DATES_DESC")
            reqs = ((data or {}).get("items") or [{}])[0].get("requisitionList") or []
            for r in reqs:
                posted = _when(r.get("PostedDate"))
                if posted and since and posted < since - timedelta(days=1):
                    return                                    # newest first: the rest are older
                locs = [r.get("PrimaryLocation") or ""] + [
                    l.get("Name") or "" for l in r.get("secondaryLocations") or []]
                city = _site_city(locs, r.get("Title"))
                if not any(in_india(l) for l in locs) or not city or not big_board_title_ok(r.get("Title")):
                    continue
                if not any(city_of(l) == city for l in locs):
                    locs.insert(0, f"{city}, India")              # city read from the title
                d = self._get(f"{api}/recruitingCEJobRequisitionDetails?expand=all&onlyData=true"
                              f'&finder=ById;Id="{r["Id"]}",siteNumber={site}')
                d = ((d or {}).get("items") or [{}])[0]
                yield {"_id": r["Id"], "_when": r.get("PostedDate"), "title": r.get("Title", ""),
                       "url": f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{r['Id']}",
                       "location": " / ".join(l for l in locs if l),
                       "work_mode_hint": r.get("WorkplaceType"),
                       "description": _plain(" ".join(filter(None, [
                           d.get("ExternalDescriptionStr"), d.get("ExternalResponsibilitiesStr"),
                           d.get("ExternalQualificationsStr")])) or r.get("ShortDescriptionStr"))}
            if len(reqs) < 25:
                break

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
        """Guess a board token from the company name and see if it answers.
        Only whole-name guesses ('bainandcompany', 'bain-and-company'), and the board
        must list at least one India job: names are often shared ('tcs' on Greenhouse
        is Thornbury Community Services), and a board with no India jobs adds nothing."""
        guesses = list(dict.fromkeys(filter(None, [
            company_key.replace(" ", ""), company_key.replace(" ", "-")])))
        for ats_type in URLS:
            for token in guesses:
                try:
                    data = self._get(URLS[ats_type].format(token=token))
                except (requests.RequestException, ValueError):
                    continue
                if data and any(in_india(j["location"]) for j in self._parse(ats_type, data)):
                    return ats_type, token
        return None, None
