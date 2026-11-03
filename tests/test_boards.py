from datetime import datetime, timedelta, timezone

from collector import pipeline
from collector.sources import ats
from collector.sources.linkedin import company_link
from collector.text import big_board_title_ok


def test_board_from_url():
    cases = {
        "https://diageo.wd3.myworkdayjobs.com/en-US/Diageo_Careers/job/Bengaluru/Brand-Manager_R1": ("workday", "diageo.wd3|Diageo_Careers"),
        "https://abc.wd1.myworkdayjobs.com/External/job/Mumbai/x_1": ("workday", "abc.wd1|External"),
        "https://eofh.fa.em2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_3001/requisitions/preview/56663": ("oracle", "eofh.fa.em2.oraclecloud.com|CX_3001"),
        "https://boards.greenhouse.io/okta/jobs/123": ("greenhouse", "okta"),
        "https://boards.greenhouse.io/embed/job_app?for=newrelic&token=1": ("greenhouse", "newrelic"),
        "https://jobs.lever.co/cred/abc": ("lever", "cred"),
        "https://jobs.ashbyhq.com/Navi%20Tech/abc": ("ashby", "Navi Tech"),
        "https://wd1.myworkdaysite.com/en-US/recruiting/wf/WellsFargoJobs/job/Bengaluru/x_R1": ("workday", "wf.wd1|WellsFargoJobs"),
        "https://careers.example.com/job/1": (None, None),
        None: (None, None),
    }
    for url, want in cases.items():
        assert ats.board_from_url(url) == want, url


def test_company_link_unwraps_linkedin():
    wrapped = "https://www.linkedin.com/jobs/view/externalApply/1?url=https%3A%2F%2Fjobs%2Elever%2Eco%2Fcred%2F1&urlHash=x"
    assert company_link(wrapped) == "https://jobs.lever.co/cred/1"
    assert company_link("https://jobs.lever.co/cred/1") == "https://jobs.lever.co/cred/1"


def test_workday_age():
    assert ats._workday_age("Posted Today") == 0
    assert ats._workday_age("Posted Yesterday") == 1
    assert ats._workday_age("Posted 4 Days Ago") == 4
    assert ats._workday_age("Posted 30+ Days Ago") == 31


def test_big_board_titles():
    assert big_board_title_ok("Brand Manager - Johnnie Walker")
    assert big_board_title_ok("Strategy Associate")
    assert not big_board_title_ok("Loan Officer")
    assert not big_board_title_ok("Machine Operator")


class FakeDB:
    def __init__(self, rows):
        self.rows, self.updates = rows, []

    def select(self, table, params):
        return self.rows

    def update(self, table, match, values):
        self.updates.append((match["company_key"], values["ats_type"], values["ats_token"]))


def test_learn_boards_only_fills_open_companies():
    db = FakeDB([{"company_key": "diageo"}])
    raws = [{"company": "Diageo", "apply_url": "https://diageo.wd3.myworkdayjobs.com/en-US/Diageo_Careers/job/x"},
            {"company": "Unknown Co", "apply_url": "https://jobs.lever.co/unknown/1"},
            {"company": "Diageo", "apply_url": None}]
    assert pipeline.learn_boards(db, raws, lambda *a: None) == 1
    assert db.updates == [("diageo", "workday", "diageo.wd3|Diageo_Careers")]


def test_workday_fetch_keeps_india_titles_in_window(monkeypatch):
    client = ats.ATS(log=lambda *a: None)
    listing = {"total": 3, "jobPostings": [
        {"title": "Brand Manager", "locationsText": "Bengaluru, India", "postedOn": "Posted 2 Days Ago", "externalPath": "/job/B/Brand-Manager_R1"},
        {"title": "Machine Operator", "locationsText": "Pune, India", "postedOn": "Posted Today", "externalPath": "/job/P/Op_R2"},
        {"title": "Strategy Lead", "locationsText": "Mumbai, India", "postedOn": "Posted 30+ Days Ago", "externalPath": "/job/M/S_R3"}]}
    monkeypatch.setattr(client, "_post", lambda url, body: listing)
    monkeypatch.setattr(client, "_get", lambda url: {"jobPostingInfo": {
        "title": "Brand Manager", "location": "Bengaluru, India", "jobDescription": "<p>MBA &amp; 3 years</p>",
        "jobReqId": "R1", "startDate": "2026-11-01", "externalUrl": "https://diageo.wd3.myworkdayjobs.com/x"}})
    jobs = client.fetch("Diageo", "workday", "diageo.wd3|Diageo_Careers",
                        datetime.now(timezone.utc) - timedelta(days=7))
    assert [j["title"] for j in jobs] == ["Brand Manager"]
