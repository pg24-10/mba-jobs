from collector.companies import IsbMatcher
from collector.pipeline import merge, normalize, salary_from_text
from collector.sources.jobspy_sources import split_or

ISB = IsbMatcher(["Amazon", "Bain & Company"])


def raw(**kw):
    base = {"source": "linkedin", "source_id": "linkedin:1", "url": "u1", "title": "Product Manager",
            "company": "Amazon Development Centre", "location": "Bengaluru, Karnataka, India"}
    return {**base, **kw}


def test_normalize_basics():
    row, _ = normalize(raw(description="We need 5-8 years of experience"), ISB)
    assert row["location_city"] == "Bangalore"
    assert row["past_isb_recruiter"] is True
    assert (row["experience_min"], row["experience_max"]) == (5, 8)
    assert row["dedupe_key"] == "amazon development centre|product manager|bangalore"


def test_drops_interns_and_internship_type():
    assert normalize(raw(title="Summer Intern"), ISB)[0] is None
    assert normalize(raw(employment_type="Internship"), ISB)[0] is None


def test_vague_location_uses_search_city():
    row, _ = normalize(raw(location="KA, India", search_city="Bangalore"), ISB)
    assert row["location_city"] == "Bangalore"


def test_salary_text():
    assert salary_from_text("₹15,00,000.00/yr - ₹25,00,000.00/yr") == (15.0, 25.0)
    assert salary_from_text("") == (None, None)


def test_merge_keeps_all_links():
    a, _ = normalize(raw(), ISB)
    b, _ = normalize(raw(source="naukri", source_id="naukri:9", url="u2"), ISB)
    [m] = merge([a, b])
    assert m["sources"] == ["linkedin", "naukri"] and m["source_links"] == ["u1", "u2"]


def test_split_or():
    assert split_or('"product manager" OR strategy') == ['"product manager"', "strategy"]


def test_trim_keeps_role_and_requirements():
    from collector.text import trim_requirements
    intro = "Acme is a leading company founded in 1990 with offices everywhere. " * 5
    role = "About the role: You will own pricing strategy for our lending products. "
    reqs = "Requirements: MBA from a top school, 3-5 years in consulting."
    out = trim_requirements(intro + role + reqs)
    assert out.startswith("About the role")
    assert "pricing strategy" in out and out.endswith("consulting.")
    assert "founded in 1990" not in out
    assert trim_requirements("x" * 5000).__len__() == 2500


def test_applicants_caption():
    from collector.sources.linkedin import applicants_of
    assert applicants_of("106 applicants") == 106
    assert applicants_of("Over 200 applicants") == 200
    assert applicants_of("Be among the first 25 applicants") == 25
    assert applicants_of("") is None


def test_unsaved_rows_kept_then_saved(tmp_path, monkeypatch):
    import pytest
    from collector import pipeline
    monkeypatch.setattr(pipeline, "UNSAVED", tmp_path)
    rows = [{"dedupe_key": "k", "title": "PM", "company": "A", "location_city": "Pune",
             "experience_min": None, "experience_max": None, "description_trimmed": None}]

    class Down:
        def upsert_jobs(self, rows):
            raise ConnectionError("no internet")

    class Up:
        def upsert_jobs(self, rows):
            return [{"id": 7, "dedupe_key": "k", "is_new": True}]

    with pytest.raises(ConnectionError):
        pipeline.save(Down(), rows, "linkedin", log=lambda *a: None)
    assert len(list(tmp_path.glob("*.json"))) == 1
    items = pipeline.save_unsaved(Up(), log=lambda *a: None)
    assert items[0]["id"] == 7 and not list(tmp_path.glob("*.json"))


def test_locations_outside_cities_and_remote_search():
    row, why = normalize(raw(location="Kochi, Kerala, India", search_city="Remote (India)"), ISB)
    assert row is None and why.startswith("outside chosen cities")
    row, _ = normalize(raw(location="India", search_city="Remote (India)"), ISB)
    assert row["location_city"] is None and row["work_mode"] != "remote"
    row, _ = normalize(raw(location="India (Remote)", search_city="Remote (India)"), ISB)
    assert row["location_city"] == "Remote (India)" and row["work_mode"] == "remote"
    row, _ = normalize(raw(location="Gurugram, Haryana, India", search_city="Remote (India)"), ISB)
    assert row["location_city"] == "Delhi NCR"


def test_known_agency_names():
    from collector.text import looks_like_agency
    assert looks_like_agency("Uplers")
    assert looks_like_agency("Michael Page India")
    assert not looks_like_agency("Haystack Analytics")


def test_jobspy_retries_then_gives_up(monkeypatch):
    import pytest
    from collector import pipeline
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    calls = []

    def fake(source, term, location, hours):
        calls.append(term)
        if len(calls) == 2:                       # the retry of the first search works
            return [{"title": "PM"}, {"title": "APM"}], []
        return [{"title": "PM"}], ["timed out"]
    monkeypatch.setattr(pipeline.jobspy_sources, "search", fake)
    groups = [{"id": "g", "query": "a OR b OR c OR d"}]
    locs = [{"name": "Bangalore", "indeed": "Bangalore"}]
    with pytest.raises(RuntimeError):
        pipeline.collect_jobspy(None, "indeed", groups, locs, pipeline.now(), log=lambda *a: None)
    assert calls == ["a", "a", "b", "b", "c", "c", "d", "d"]   # gives up after 3 failing in a row


class _KnownDB:
    def __init__(self, known=()):
        self.known = set(known)

    def known_source_ids(self, ids):
        return self.known & set(ids)

    def described_keys(self, keys):
        return set()


def test_naukri_captcha_on_search_pauses_naukri(monkeypatch):
    import pytest
    from collector import pipeline
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    monkeypatch.setattr(pipeline.jobspy_sources, "search",
                        lambda *a: ([], ["response status code 406 (recaptcha required)"]))
    groups = [{"id": "g", "query": "a OR b"}]
    locs = [{"name": "Bangalore", "naukri": "Bangalore"}]
    with pytest.raises(pipeline.Blocked):
        pipeline.collect_jobspy(None, "naukri", groups, locs, pipeline.now(), log=lambda *a: None)


def _naukri(i, title):
    return {"source": "naukri", "source_id": f"naukri:nk-{i}", "title": title, "company": "Acme",
            "location": "Bengaluru", "description": None, "industry": None}


def test_naukri_opens_only_new_matching_jobs(monkeypatch):
    from collector import pipeline
    opened = []

    class Pages:
        def __init__(self, delay): pass

        def details(self, job_id):
            opened.append(job_id)
            return {"description": "about the role", "industry": "Fintech"}
    monkeypatch.setattr(pipeline.jobspy_sources, "NaukriPages", Pages)
    raws = [_naukri(1, "Product Manager"), _naukri(2, "Product Manager"),
            _naukri(3, "Java Developer"), _naukri(1, "Product Manager")]
    out = pipeline.naukri_details(_KnownDB({"naukri:nk-2"}), raws, {}, log=lambda *a: None)
    assert opened == ["1"]                        # 2 is already saved, 3 is not an MBA title
    assert len(out) == 3
    assert out[0]["description"] == "about the role"


def test_naukri_block_keeps_pages_opened_so_far(monkeypatch):
    import pytest
    from collector import pipeline

    class Pages:
        def __init__(self, delay): self.n = 0

        def details(self, job_id):
            self.n += 1
            if self.n == 2:
                raise pipeline.Blocked("captcha")
            return {"description": "d"}
    monkeypatch.setattr(pipeline.jobspy_sources, "NaukriPages", Pages)
    raws = [_naukri(1, "Product Manager"), _naukri(2, "Product Lead"), _naukri(3, "Product Owner")]
    with pytest.raises(pipeline.Blocked) as e:
        pipeline.naukri_details(_KnownDB(), raws, {}, log=lambda *a: None)
    assert [r["source_id"] for r in e.value.partial] == ["naukri:nk-1", "naukri:nk-2", "naukri:nk-3"]
    assert [r["description"] for r in e.value.partial] == ["d", None, None]   # 2 and 3 keep their summary


def test_naukri_uses_search_text_and_opens_only_short_summaries(monkeypatch):
    from collector import pipeline
    opened = []

    class Pages:
        def __init__(self, delay): pass

        def details(self, job_id):
            opened.append(job_id)
            return {"description": "the full text " * 20, "industry": "Fintech"}
    monkeypatch.setattr(pipeline.jobspy_sources, "NaukriPages", Pages)
    full, summary = _naukri(1, "Product Manager"), _naukri(2, "Product Manager")
    full["description"], full["skills"] = "word " * 80, "Pricing, Strategy"
    summary["description"] = "Lead product for payments."
    out = pipeline.naukri_details(_KnownDB(), [full, summary], {}, log=lambda *a: None)
    assert opened == ["2"]                         # 1's search text is already the whole description
    assert out[0]["description"].endswith("Key skills: Pricing, Strategy")
    assert out[1]["description"].startswith("the full text")
    assert "skills" not in out[0]


def test_linkedin_block_keeps_details_fetched_so_far(monkeypatch):
    import pytest
    from collector import pipeline

    class LI:
        requests = blocks = 0

        def __init__(self, log): self.n = 0

        def search(self, *a, **k):
            yield from ({"id": str(i), "title": t, "company": "Acme", "location": "Bengaluru", "posted": None}
                        for i, t in [(1, "Product Manager"), (2, "Java Developer"), (3, "Product Lead")])

        def detail(self, i):
            self.n += 1
            if self.n == 2:
                raise pipeline.Blocked("429")
            return {"description": "d"}
    monkeypatch.setattr(pipeline, "LinkedIn", LI)
    groups = [{"id": "product", "query": '"product manager"'}]
    locs = [{"name": "Bangalore", "linkedin": "Bengaluru"}]
    with pytest.raises(pipeline.Blocked) as e:
        pipeline.collect_linkedin(_KnownDB(), groups, locs, pipeline.now() - pipeline.timedelta(days=1),
                                  log=lambda *a: None)
    assert [r["source_id"] for r in e.value.partial] == ["linkedin:1"]   # 2 not worth opening


def test_skips_pages_for_jobs_already_described_elsewhere():
    from collector import pipeline

    class DB(_KnownDB):
        def described_keys(self, keys):
            return {k for k in keys if "product manager" in k}
    raws = [_naukri(1, "Product Manager"), _naukri(2, "Product Lead"),
            {**_naukri(3, "Product Owner"), "location": "Kochi"}]
    assert pipeline.not_worth_opening(DB(), raws) == {"naukri:nk-1", "naukri:nk-3"}


def test_naukri_search_row_keeps_its_description():
    from jobspy.model import ScraperInput, Site
    from jobspy.naukri import Naukri
    from collector.sources import jobspy_sources

    jobspy_sources._keep_naukri_search_text()
    jobspy_sources._keep_naukri_search_text()                # patching twice is harmless
    n = Naukri()
    n.scraper_input = ScraperInput(site_name=[Site.NAUKRI], search_term="x", fetch_description=False,
                                   description_format="markdown")
    row = {"jobId": "1", "companyApplyJob": False, "title": "Strategy Manager", "companyName": "Acme",
           "staticUrl": None, "jdURL": "/job-1", "logoPathV3": None, "createdDate": 1793773751311,
           "employmentType": "Full Time, Permanent", "tagsAndSkills": "Pricing,Strategy",
           "placeholders": [{"type": "location", "label": "Mumbai"}, {"type": "salary", "label": "Not disclosed"}],
           "salaryDetail": {"hideSalary": True, "minimumSalary": 0, "maximumSalary": 0, "currency": "INR"},
           "jobDescription": "<p>Own <strong>pricing</strong> strategy.</p>"}
    post = n._process_job(row)
    assert "pricing" in post.description and "<p>" not in post.description
    assert post.skills == ["Pricing", "Strategy"]


# ------------------------------------------------ LinkedIn steps, time limit, carry-over

def _step_li(block_at=None):
    """Fake LinkedIn: each search returns one card named after the city; the
    `block_at`-th search raises TimeUp."""
    from collector import pipeline

    class LI:
        requests = blocks = 0
        searches = []

        def __init__(self, log): pass

        def search(self, query, place, seconds, extra=None):
            LI.searches.append(place)
            if len(LI.searches) == block_at:
                raise pipeline.TimeUp("time limit")
            yield {"id": place, "title": "Product Manager", "company": "Acme", "location": place, "posted": None}

        def detail(self, i):
            return {"description": "d"}
    return LI


_GROUPS = [{"id": "product", "query": '"product manager"'}]
_LOCS = [{"name": c, "linkedin": c} for c in ("Mumbai", "Pune", "Delhi")]


def test_linkedin_saves_each_step_and_starts_where_told(monkeypatch):
    from collector import pipeline
    LI = _step_li()
    monkeypatch.setattr(pipeline, "LinkedIn", LI)
    batches = []
    out = pipeline.collect_linkedin(_KnownDB(), _GROUPS, _LOCS, pipeline.now() - pipeline.timedelta(days=1),
                                    log=lambda *a: None, flush=batches.append, first_step=1)
    assert LI.searches == ["Pune", "Delhi", "Mumbai"]                    # wraps round
    assert [[r["source_id"] for r in b] for b in batches] == [["linkedin:Pune"], ["linkedin:Delhi"],
                                                              ["linkedin:Mumbai"]]
    assert out == []                                                     # all handed to flush


def test_linkedin_time_up_keeps_finished_steps_and_says_where_to_resume(monkeypatch):
    import pytest
    from collector import pipeline
    monkeypatch.setattr(pipeline, "LinkedIn", _step_li(block_at=2))
    batches = []
    with pytest.raises(pipeline.TimeUp) as e:
        pipeline.collect_linkedin(_KnownDB(), _GROUPS, _LOCS, pipeline.now() - pipeline.timedelta(days=1),
                                  log=lambda *a: None, flush=batches.append)
    assert [[r["source_id"] for r in b] for b in batches] == [["linkedin:Mumbai"], []]
    assert e.value.next_step == 1                                        # Pune again next time


def test_linkedin_client_stops_at_deadline_instead_of_resting(monkeypatch):
    import pytest
    from collector.sources import TimeUp
    from collector.sources import linkedin
    li = linkedin.LinkedIn(log=lambda *a: None)
    li.deadline = linkedin.time.time() + 60                               # one minute left
    with pytest.raises(TimeUp):
        li._push_back(429)                                               # the first rest is 5 min
    li.deadline = linkedin.time.time() - 1
    with pytest.raises(TimeUp):
        li._get("https://example.invalid")                               # no request once time is up


class _RunsDB(_KnownDB):
    def __init__(self, last=None):
        super().__init__()
        self.last, self.inserted, self.updated, self.upserts = last, [], [], []

    def select(self, table, params):
        if params.get("status") == "eq.success":                         # window_start: no success yet
            return []
        return [self.last] if self.last else []

    def insert(self, table, row):
        self.inserted.append(row)
        return {"run_id": len(self.inserted)}

    def update(self, table, match, values):
        self.updated.append(values)

    def upsert_jobs(self, rows):
        self.upserts.append(rows)
        return [{"dedupe_key": r["dedupe_key"], "id": n, "is_new": True} for n, r in enumerate(rows)]

    def rpc(self, name):
        return 0


def test_next_step_reads_the_last_stopped_run():
    from collector import pipeline
    assert pipeline.next_step(_RunsDB(), "linkedin") == 0
    assert pipeline.next_step(_RunsDB({"status": "success", "errors": None}), "linkedin") == 0
    stopped = {"status": "pending", "errors": "linkedin reached the time limit. Left for a later run "
                                              "(carry on from step 7)."}
    assert pipeline.next_step(_RunsDB(stopped), "linkedin") == 6


def test_daily_run_saves_linkedin_per_step_and_marks_time_up_as_pending(monkeypatch, tmp_path):
    from collector import pipeline
    monkeypatch.setattr(pipeline, "LinkedIn", _step_li(block_at=3))
    monkeypatch.setattr(pipeline, "learn_boards", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "write_inbox", lambda items: None)
    monkeypatch.setattr(pipeline, "write_run_log", lambda summary: None)
    monkeypatch.setattr(pipeline, "UNSAVED", tmp_path / "unsaved")
    stopped = {"status": "pending", "errors": "linkedin blocked: 429. Left for a later run (carry on from step 2)."}
    db = _RunsDB(stopped)
    summary = pipeline.run(db, ["linkedin"], _GROUPS, _LOCS, isb=ISB, log=lambda *a: None)
    assert len(db.upserts) == 2                                          # Pune, Delhi saved one by one
    assert summary["linkedin"]["new"] == 2 and summary["linkedin"]["status"] == "pending"
    assert db.updated[-1]["status"] == "pending"                         # window stays put
    assert "carry on from step 1" in db.updated[-1]["errors"]            # Mumbai is next



def _jobspy_fake(monkeypatch, calls):
    from collector import pipeline
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)

    def fake(source, term, location, hours):
        calls.append((term, location))
        return [{"title": f"{term} {location}"}], []
    monkeypatch.setattr(pipeline.jobspy_sources, "search", fake)
    return [{"id": "g", "query": "a OR b OR c"}], [{"name": "X", "indeed": "X"}, {"name": "Y", "indeed": "Y"}]


def test_jobspy_saves_after_every_search_and_stops_at_the_time_limit(monkeypatch):
    import pytest
    from collector import pipeline
    calls, saved = [], []
    groups, locs = _jobspy_fake(monkeypatch, calls)
    clock = iter([0, 0, 0, 10_000])                      # time runs out before the 4th search
    monkeypatch.setattr(pipeline.time, "time", lambda: next(clock))
    with pytest.raises(pipeline.TimeUp) as e:
        pipeline.collect_jobspy(None, "indeed", groups, locs, pipeline.now(), log=lambda *a: None,
                                flush=saved.append, deadline=1000)
    assert len(saved) == 3 and e.value.next_step == 3


def test_jobspy_carries_on_and_splits_across_machines(monkeypatch):
    from collector import pipeline
    calls = []
    groups, locs = _jobspy_fake(monkeypatch, calls)
    pipeline.collect_jobspy(None, "indeed", groups, locs, pipeline.now(), log=lambda *a: None, first_step=4)
    assert calls[:2] == [("c", "X"), ("c", "Y")] and len(calls) == 6     # wraps round to the start
    calls.clear()
    pipeline.collect_jobspy(None, "indeed", groups, locs, pipeline.now(), log=lambda *a: None, shard=(2, 3))
    assert calls == [("a", "Y"), ("c", "X")]                           # searches 2 and 5 of 6


class _ParamsDB:
    def __init__(self, rows):
        self.rows, self.params = rows, None

    def select(self, table, params):
        self.params = params
        return self.rows


def test_split_machines_catch_up_from_their_own_last_run():
    from collector import pipeline
    db = _ParamsDB([{"status": "pending", "errors": "linkedin reached the time limit. Left for a later run "
                                                     "(carry on from step 23)."}])
    assert pipeline.next_step(db, "linkedin", (3, 10)) == 22
    assert db.params["machine"] == "like.* 3/10" and db.params["status"] == "in.(partial,pending)"
    pipeline.next_step(db, "linkedin")
    assert db.params["machine"] == "not.like.*/*"                       # whole runs ignore split ones
    db = _ParamsDB([])
    pipeline.window_start(db, "linkedin", shard=(3, 10))
    assert "machine.like.* 3/10" in db.params["or"] and "status" not in db.params
    pipeline.window_start(db, "linkedin")
    assert db.params["status"] == "eq.success"


def test_naukri_never_looks_back_more_than_a_day():
    from datetime import timedelta
    from collector import pipeline
    old = [{"finished_at": "2026-11-04T10:00:00+00:00"}]               # last success long ago
    start = pipeline.window_start(_ParamsDB(old), "naukri", shard=(2, 5))
    assert pipeline.now() - start <= timedelta(days=1, seconds=5)
    start = pipeline.window_start(_ParamsDB(old), "indeed")             # others still catch up
    assert pipeline.now() - start > timedelta(days=5)
