from datetime import datetime, timedelta, timezone

from collector.sources import careers_site as cs

PAGE = '''<html><script type="application/ld+json">{"@context":"https://schema.org","@graph":[
 {"@type":"WebPage"},
 {"@type":"JobPosting","title":"Strategy Manager","datePosted":"2026-11-01","identifier":{"value":"R42"},
  "employmentType":"FULL_TIME","description":"<p>MBA &amp; 4 years</p>",
  "jobLocation":{"@type":"Place","address":{"addressLocality":"Bengaluru","addressRegion":"KA","addressCountry":"IN"}}}]}
</script></html>'''

SITEMAP_INDEX = '''<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://careers.acme.com/sitemap-pages.xml</loc></sitemap>
<sitemap><loc>https://careers.acme.com/sitemap-jobs.xml</loc></sitemap></sitemapindex>'''

JOBS = '''<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://careers.acme.com/job/strategy-manager-bengaluru-r42</loc><lastmod>2026-11-01</lastmod></url>
<url><loc>https://careers.acme.com/job/forklift-driver-pune-r43</loc><lastmod>2026-11-01</lastmod></url>
<url><loc>https://careers.acme.com/job/brand-manager-mumbai-r44</loc><lastmod>2026-01-01</lastmod></url>
</urlset>'''


class FakeClient:
    def __init__(self, pages):
        self.pages, self.asked = pages, []
        self.http = type("H", (), {"headers": {"User-Agent": "mba-jobs/1.0"}})()

    def _text(self, url):
        self.asked.append(url)
        return self.pages.get(url)


def site(extra=None):
    pages = {"https://careers.acme.com/robots.txt": "User-agent: *\nDisallow: /search\nSitemap: https://careers.acme.com/sitemap.xml",
             "https://careers.acme.com/sitemap.xml": SITEMAP_INDEX,
             "https://careers.acme.com/sitemap-jobs.xml": JOBS,
             "https://careers.acme.com/job/strategy-manager-bengaluru-r42": PAGE}
    pages.update(extra or {})
    client = FakeClient(pages)
    return client, cs.CareersSite(client, "careers.acme.com")


def test_careers_host():
    assert cs.careers_host("https://careers.acme.com/job/1") == "careers.acme.com"
    assert cs.careers_host("https://in.indeed.com/viewjob?jk=1") is None
    assert cs.careers_host("https://jobs.smartrecruiters.com/Acme/1") is None
    assert cs.careers_host(None) is None


def test_reads_job_pages_from_sitemap():
    client, s = site()
    assert s.check()
    jobs = list(s.jobs(datetime(2026, 10, 25, tzinfo=timezone.utc)))
    assert [j["title"] for j in jobs] == ["Strategy Manager"]
    j = jobs[0]
    assert j["_id"] == "R42" and j["location"] == "Bengaluru, KA, India"
    assert j["description"] == "MBA & 4 years"
    # the forklift page is skipped from its address; the old brand page by its date
    assert not any("forklift" in u or "brand-manager" in u for u in client.asked)
    assert "https://careers.acme.com/sitemap-pages.xml" not in client.asked   # the job sitemap is enough


def test_respects_robots():
    client, s = site({"https://careers.acme.com/robots.txt": "User-agent: *\nDisallow: /"})
    assert not s.check()
    assert client.asked == ["https://careers.acme.com/robots.txt"]


def test_site_without_tags_fails_check():
    _, s = site({"https://careers.acme.com/job/strategy-manager-bengaluru-r42": "<html>no tags</html>"})
    assert not s.check()
