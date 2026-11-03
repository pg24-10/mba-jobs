"""A company's own careers site, read the way Google Jobs reads it.

Many careers sites tag each job page with a schema.org `JobPosting` block (JSON-LD)
so Google can list it, and list the job pages in their sitemap. We do the same:
  1. robots.txt: skip the site if it disallows us; note the sitemaps it names
  2. sitemap(s): job-looking page links (with "last changed" dates when given)
  3. each new job page: read its JobPosting block

The careers host is learned from a job's company apply link (see learn_boards in
pipeline.py) and checked once before it is saved; the token is just the host,
e.g. "careers.example.com". Sites without a sitemap or JobPosting tags are
marked "none" and checked again a month later.
"""

import json
import re
from datetime import timedelta
from urllib import robotparser
from urllib.parse import urlparse
from xml.etree import ElementTree

from ..settings import config
from ..text import big_board_title_ok, fold

JOB_PATH = re.compile(r"job|career|position|opening|vacanc|requisition|role", re.I)

# Job sites and careers systems we read another way, or that ask not to be read
NOT_A_CAREERS_SITE = re.compile(
    r"(^|\.)(indeed|naukri|linkedin|glassdoor|foundit|monster|shine|iimjobs|hirist|instahyre|"
    r"cutshort|wellfound|apna|timesjobs|smartrecruiters|eightfold|greenhouse|lever|ashbyhq|"
    r"myworkdayjobs|oraclecloud|google|bit|lnkd)\.[a-z.]+$", re.I)


def careers_host(url):
    """Apply link -> the careers site's host, or None for job sites and odd links."""
    host = (urlparse(url or "").hostname or "").lower()
    if not host or NOT_A_CAREERS_SITE.search(host) or re.fullmatch(r"[\d.]+", host):
        return None
    return host


def _settings():
    return config("settings")["ats"].get("careers_site", {})


class CareersSite:
    """Reads one host through an ATS client (shared pacing, session and User-Agent)."""

    def __init__(self, client, host):
        self.client, self.host, self.base = client, host, f"https://{host}"
        self._robots = None

    # ------------------------------------------------------------ robots + sitemaps

    def robots(self):
        if self._robots is None:
            rp = robotparser.RobotFileParser()
            text = self.client._text(f"{self.base}/robots.txt")
            rp.parse((text or "").splitlines())          # no robots.txt: everything allowed
            self._robots = rp
        return self._robots

    def allowed(self, url):
        return self.robots().can_fetch(self.client.http.headers["User-Agent"], url)

    def job_links(self):
        """[(url, lastmod or None)] for job-looking pages in the site's sitemaps."""
        s = _settings()
        todo = list(self.robots().site_maps() or []) or [f"{self.base}/sitemap.xml"]
        seen, links = set(), []
        while todo and len(seen) < int(s.get("max_sitemaps", 6)):
            url = todo.pop(0)
            if url in seen or not self.allowed(url):
                continue
            seen.add(url)
            root = _xml(self.client._text(url))
            if root is None:
                continue
            if _tag(root) == "sitemapindex":
                kids = [_find(e, "loc") for e in root if _tag(e) == "sitemap"]
                kids = [k for k in kids if k]
                todo += [k for k in kids if JOB_PATH.search(urlparse(k).path)] or kids[:3]
                continue
            for e in root:
                loc = _find(e, "loc")
                if loc and JOB_PATH.search(urlparse(loc).path) and urlparse(loc).path.strip("/"):
                    links.append((loc, _find(e, "lastmod")))
        return links

    # ------------------------------------------------------------ job pages

    def posting(self, url):
        """The JobPosting block on a page, or None."""
        if not self.allowed(url):
            return None
        page = self.client._text(url) or ""
        for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
            try:
                data = json.loads(block.strip())
            except ValueError:
                continue
            for item in _items(data):
                if "jobposting" in fold(str(item.get("@type"))):
                    return item
        return None

    def check(self):
        """True if the site lists job pages and at least one carries a JobPosting tag."""
        links = self.job_links()
        return any(self.posting(u) for u, _ in links[-3:] + links[:2])

    def jobs(self, since):
        """Raw jobs (ats.fetch shape) for job pages changed since `since`."""
        from .ats import _when

        s = _settings()
        links = self.job_links()
        if since:
            links = [(u, m) for u, m in links if not m or not _when(m) or _when(m) >= since - timedelta(days=1)]
        opened = 0
        for url, _ in links:
            slug = re.sub(r"[-_/]+", " ", urlparse(url).path)
            words = re.findall(r"[a-z]{3,}", slug.lower())
            if len(words) >= 3 and not big_board_title_ok(slug):   # the address names a non-MBA title
                continue
            if opened >= int(s.get("max_pages", 40)):
                break
            opened += 1
            p = self.posting(url)
            if not p or not big_board_title_ok(p.get("title")):
                continue
            yield {"_id": _ident(p) or urlparse(url).path,
                   "_when": p.get("datePosted"),
                   "title": _plain(p.get("title")),
                   "url": p.get("url") or url,
                   "location": _where(p),
                   "employment_type": ", ".join(p["employmentType"]) if isinstance(p.get("employmentType"), list)
                                      else p.get("employmentType"),
                   "work_mode_hint": "remote" if "telecommute" in fold(str(p.get("jobLocationType"))) else None,
                   "description": _plain(p.get("description"))}


# ------------------------------------------------------------ helpers

def _xml(text):
    if not text or "<" not in text[:200]:
        return None
    try:
        return ElementTree.fromstring(text.encode())
    except ElementTree.ParseError:
        return None


def _tag(e):
    return e.tag.rsplit("}", 1)[-1].lower()


def _find(e, name):
    for child in e:
        if _tag(child) == name:
            return (child.text or "").strip() or None
    return None


def _items(data):
    if isinstance(data, list):
        for d in data:
            yield from _items(d)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _items(data["@graph"])


def _ident(p):
    i = p.get("identifier")
    return str(i.get("value") or i.get("name")) if isinstance(i, dict) else (str(i) if i else None)


def _where(p):
    """jobLocation (one or a list of Place / PostalAddress) -> 'Bengaluru, Karnataka, India / ...'."""
    places = p.get("jobLocation") or []
    out = []
    for place in places if isinstance(places, list) else [places]:
        a = place.get("address", place) if isinstance(place, dict) else {}
        if isinstance(a, str):
            out.append(a)
            continue
        country = a.get("addressCountry")
        country = country.get("name") if isinstance(country, dict) else country
        country = "India" if str(country).upper() in ("IN", "IND") else country
        out.append(", ".join(str(x) for x in [a.get("addressLocality"), a.get("addressRegion"), country] if x))
    if not any(out) and "telecommute" in fold(str(p.get("jobLocationType"))):
        req = p.get("applicantLocationRequirements") or {}
        out.append(f"Remote, {req.get('name', '') if isinstance(req, dict) else req}")
    return " / ".join(o for o in out if o)


def _plain(fragment):
    from .ats import _plain as plain
    return plain(fragment if isinstance(fragment, str) else "")
