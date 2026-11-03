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
    locs = [{"name": "Bangalore", "naukri": "Bangalore"}]
    with pytest.raises(RuntimeError):
        pipeline.collect_jobspy("naukri", groups, locs, pipeline.now(), log=lambda *a: None)
    assert calls == ["a", "a", "b", "b", "c", "c", "d", "d"]   # gives up after 3 failing in a row
