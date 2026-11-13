"""The coverage check sorts campus roles into found / company only / missing."""

from collector.coverage import check, same_company


def test_check_sorts_roles():
    jobs = {"mckinsey": [{"title": "Associate - Strategy & Operations", "sources": ["linkedin"]}],
            "amazon": [{"title": "Senior Software Engineer", "sources": ["ats"]}]}
    roles = [{"company": "McKinsey & Company", "title": "Associate"},
             {"company": "Amazon", "title": "Senior Product Manager"},
             {"company": "Unknown Co Pvt Ltd", "title": "Manager"}]
    rows = check(roles, lambda k: jobs.get(k, []))
    assert [r["result"] for r in rows] == ["found", "company only", "missing"]
    assert rows[0]["found on"] == "linkedin"


def test_same_company():
    assert same_company("accenture solutions", "accenture")
    assert same_company("ey", "ey parthenon")
    assert not same_company("jsw paints", "jsw steel")
    assert not same_company("ubs", "ubsx")
