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
