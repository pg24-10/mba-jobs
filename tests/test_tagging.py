from collector.settings import config
from collector.tagging import fit_score


def test_every_function_has_a_starting_score():
    tags = config("tags")
    assert set(tags["fit_start"]) == set(tags["function"])


def test_fit_score_steps():
    pm = {"function": "product", "seniority": "manager", "hands_on": False, "mba_requirement": "not mentioned"}
    assert fit_score(pm) == 5
    assert fit_score({**pm, "seniority": "director"}) == 4                      # beyond most MBA hires
    assert fit_score({**pm, "function": "operations", "mba_requirement": "preferred"}) == 4
    sap = {"function": "technology", "seniority": "entry", "hands_on": True, "mba_requirement": "not mentioned"}
    assert fit_score(sap) == 1                                                   # never below 1
    assert fit_score({**pm, "mba_requirement": "required"}) == 5                 # never above 5
    assert fit_score({"function": "unknown"}) == 2


import json

import pytest

from collector import tagging
from collector.tagging import check, copied


@pytest.fixture(autouse=True)
def _own_folder(tmp_path, monkeypatch):
    """Tests never touch the real data/state/tagging files."""
    monkeypatch.setattr(tagging, "DIR", tmp_path)
    monkeypatch.setattr(tagging, "FAILED", tmp_path / "failed.json")
    monkeypatch.setattr(tagging, "DUPES", tmp_path / "dupes.json")

POST = ("We are hiring a product manager to own the payments roadmap for small merchants across India "
        "and work closely with engineering, design and sales teams every single day.")
GOOD = {"id": 1, "function": "product", "seniority": "manager", "background_wanted": ["mba", "product"],
        "mba_requirement": "preferred", "masters_mentioned": False, "industry": "fintech",
        "industry_experience_required": "not mentioned", "company_type": "startup", "startup_stage": "growth",
        "experience_min": 4, "experience_max": 7, "hands_on": False,
        "summary": "Lead the payments product for small shops.",
        "duties": ["Set the roadmap for merchant payments", "Run releases with tech and design"],
        "looking_for": ["Some product experience"], "key_skills": ["roadmaps", "payments"]}
JOB = {"id": 1, "title": "Product Manager", "description": POST, "experience_min": None, "experience_max": None}


def test_copied_spots_eight_words_in_a_row():
    assert copied(["Own the payments roadmap for small merchants across India and more"], POST)
    assert not copied(["Lead the payments product for small shops"], POST)


def test_check_saves_a_good_tag_with_fit_from_code():
    row = check({**GOOD, "fit_score": 1}, JOB, config("tags"))
    assert row["fit_score"] == 5 and row["startup_stage"] == "growth"
    assert "experience_min" not in row                      # the post states no years


def test_code_reads_years_and_masters_not_claude():
    post = POST + " You need 4-7 years of experience and an MBA or master's degree."
    row = check({**GOOD, "experience_min": 1, "masters_mentioned": False}, {**JOB, "description": post},
                config("tags"))
    assert (row["experience_min"], row["experience_max"], row["masters_mentioned"]) == (4.0, 7.0, True)


def test_read_years():
    assert tagging.read_years("Minimum 5+ years of relevant experience") == (5.0, None)
    assert tagging.read_years("Experience: 3 to 6 yrs in sales") == (3.0, 6.0)
    assert tagging.read_years("2 years experience in Excel; overall 8-10 years of experience") == (8.0, 10.0)
    assert tagging.read_years("We have grown 3x in 4 years") == (None, None)  # not about experience


def test_already_known_fills_mba_and_listed_company():
    facts = {tagging._key("Randstad"): (None, "agency")}
    known = tagging.already_known({"company": "Randstad", "description": POST}, facts)
    assert known == {"mba_requirement": "not mentioned", "company_type": "agency", "startup_stage": None}
    assert tagging.already_known({"company": "Y", "description": "MBA from a top school"}, facts) == {}
    row = check({**GOOD, "function": "marketing", "mba_requirement": "required", "company_type": "mnc"},
                {**JOB, "already_known": {"mba_requirement": "not mentioned"}}, config("tags"))
    assert row["mba_requirement"] == "not mentioned" and row["fit_score"] == 4  # code wins


def test_check_accepts_tags_without_the_known_fields():
    tag = {k: v for k, v in GOOD.items() if k not in ("mba_requirement", "industry", "company_type",
                                                      "startup_stage", "masters_mentioned",
                                                      "experience_min", "experience_max")}
    known = {"mba_requirement": "not mentioned", "industry": "fintech", "company_type": "mnc", "startup_stage": None}
    row = check(tag, {**JOB, "already_known": known}, config("tags"))
    assert row["industry"] == "fintech" and row["startup_stage"] is None


def test_title_model():
    past = ([{"title": "SAP ABAP Developer", "fit_score": 1}] * 30 +
            [{"title": "Product Manager", "fit_score": 5}] * 30 + [{"title": "Sales Manager", "fit_score": 3}] * 10)
    model = tagging.title_model(past)
    assert tagging.p_low(model, "Senior SAP ABAP Developer") > 0.99
    assert tagging.p_low(model, "Product Manager, Payments") < 0.01
    assert tagging.p_low(tagging.title_model([]), "anything") == 0.0


def test_check_refuses_bad_values_and_copying():
    tags = config("tags")
    assert "function" in check({**GOOD, "function": "wizardry"}, JOB, tags)
    assert "hands_on" in check({**GOOD, "hands_on": "no"}, JOB, tags)
    assert "background_wanted" in check({**GOOD, "background_wanted": []}, JOB, tags)
    assert "copied" in check({**GOOD, "summary": "Own the payments roadmap for small merchants across India"},
                             JOB, tags)


def test_check_keeps_known_years_and_drops_stage_for_non_startups():
    row = check({**GOOD, "company_type": "mnc"}, {**JOB, "experience_min": 3}, config("tags"))
    assert row["startup_stage"] is None and "experience_min" not in row


class FakeDB:
    def __init__(self):
        self.updates = []

    def select(self, table, params):
        return [{"id": 1, "experience_min": None, "experience_max": None},
                {"id": 2, "experience_min": None, "experience_max": None}]

    def update(self, table, match, values):
        self.updates.append((match, values))


def test_import_saves_good_tags_deletes_descriptions_and_counts_refusals(tmp_path, monkeypatch):
    monkeypatch.setattr(tagging, "FAILED", tmp_path / "failed.json")
    batch, tagged = tmp_path / "batch.json", tmp_path / "tagged.json"
    batch.write_text(json.dumps([JOB, {**JOB, "id": 2, "title": "Other"}]))
    tagged.write_text(json.dumps([GOOD, {**GOOD, "id": 2, "industry": "space"}, {**GOOD, "id": 9}]))
    db = FakeDB()
    saved, problems = tagging.import_tags(db, tagged, batch)
    assert saved == 1 and len(problems) == 2
    match, values = db.updates[0]
    assert match == {"id": 1} and values["description_trimmed"] is None and values["tagged_at"]
    assert json.loads((tmp_path / "failed.json").read_text()) == {"2": 1}


def test_import_gives_the_same_tags_to_same_title_jobs(tmp_path):
    batch, tagged = tmp_path / "batch.json", tmp_path / "tagged.json"
    batch.write_text(json.dumps([JOB]))
    tagged.write_text(json.dumps([GOOD]))
    (tmp_path / "dupes.json").write_text(json.dumps({"1": [
        {"id": 5, "masters_mentioned": True, "experience_min": 3.0, "experience_max": None, "has_years": False},
        {"id": 6, "masters_mentioned": False, "experience_min": None, "experience_max": None, "has_years": True}]}))
    db = PagingDB([])
    db.updates = []
    db.update = lambda table, match, values: db.updates.append((match, values))
    db.select = lambda table, params: [{"id": 1, "experience_min": None, "experience_max": None}]
    assert tagging.import_tags(db, tagged, batch, log=lambda m: None) == (1, [])
    copies = {i: v for i, v in db.patched}
    assert copies[5]["summary"] == GOOD["summary"] and copies[5]["experience_min"] == 3.0
    assert copies[5]["masters_mentioned"] and copies[5]["description_trimmed"] is None
    assert "experience_min" not in copies[6] and copies[6]["tag_model"] == "haiku-copy"
    assert json.loads((tmp_path / "dupes.json").read_text()) == {}


def test_parts_export_and_import(tmp_path, monkeypatch):
    jobs = [{"id": i, "title": "PM", "company": "X", "city": "Pune", "description": POST} for i in (1, 2, 3)]

    def fake_export(db, limit, path):
        path.write_text(json.dumps(jobs[:limit]))
        return min(limit, 3)
    monkeypatch.setattr(tagging, "export", fake_export)
    assert tagging.export_parts(None, 2, size=2) == [2, 1]
    try:
        tagging.export_parts(None, 2, size=2)
        assert False, "should refuse while parts are waiting"
    except RuntimeError:
        pass
    (tmp_path / "part1-tagged.json").write_text(json.dumps([GOOD, {**GOOD, "id": 2}]))
    db = FakeDB()
    saved, problems, left = tagging.import_parts(db)
    assert (saved, problems, left) == (2, [], 1)
    assert not (tmp_path / "part1.json").exists() and (tmp_path / "part2.json").exists()


class PagingDB:
    """Hands out untagged jobs like Supabase: flagged, skipped and tagged ones drop out of later pages."""
    base = "x"

    def __init__(self, jobs, tagged=()):
        self.jobs, self.tagged, self.flagged, self.skipped, self.patched = jobs, list(tagged), set(), set(), []

    def _send(self, method, url, params=None, headers=None, data=None, timeout=None):
        ids = [int(i) for i in params["id"][4:-1].split(",")] if str(params.get("id", "")).startswith("in.") else []
        if method == "PATCH":
            values = json.loads(data)
            if values.get("too_thin"):
                self.flagged |= set(ids)
            elif values.get("tag_skipped"):
                self.skipped |= set(ids)
            else:
                self.patched += [(i, values) for i in ids]
            return None
        start, end = map(int, headers["Range"].split("-"))
        if ids:
            rows = [t for t in self.tagged if t["id"] in ids]
        elif params.get("tagged_at") == "not.is.null":
            rows = self.tagged
        else:
            gone = self.flagged | self.skipped | {i for i, _ in self.patched}
            rows = [j for j in self.jobs if j["id"] not in gone]
        return rows[start:end + 1]


def _job(i, title, description=" ".join(["word"] * 80), company="X"):
    return {"id": i, "title": title, "company": company, "location_city": "Pune",
            "description_trimmed": description, "experience_min": None, "experience_max": None}


def test_export_leaves_out_and_flags_thin_posts(tmp_path):
    short = "Hiring a manager. Apply now."
    jobs = [_job(i, f"PM {i}", short if i % 2 else " ".join(["word"] * 80)) for i in range(1, 9)]
    db = PagingDB(jobs)
    assert tagging.export(db, 3, tmp_path / "b.json", log=lambda m: None) == 3
    assert [j["id"] for j in json.loads((tmp_path / "b.json").read_text())] == [2, 4, 6]
    assert db.flagged == {1, 3, 5}


def test_export_skips_low_titles_groups_same_titles_and_reuses_old_tags(tmp_path):
    past = ([{"id": 100 + i, "company": "Y", "title": "SAP ABAP Developer", "fit_score": 1} for i in range(30)] +
            [{"id": 200 + i, "company": "Y", "title": f"Product Manager {i}", "fit_score": 5} for i in range(30)])
    past[30] = {**past[30], **{k: GOOD[k] for k in tagging.TAG_COLS if k in GOOD}, "fit_score": 5}
    jobs = [_job(1, "SAP ABAP Developer", company="Z"),           # almost surely fit 1-2: skipped
            _job(2, "Strategy Manager"), _job(3, "Strategy  manager"),   # same company + title: one sent
            _job(4, "Product Manager 0", company="Y"),             # same as a tagged job: copied now
            _job(5, "Growth Lead")]
    db = PagingDB(jobs, past)
    assert tagging.export(db, 5, tmp_path / "b.json", log=lambda m: None) == 2
    assert [j["id"] for j in json.loads((tmp_path / "b.json").read_text())] == [2, 5]
    assert db.skipped == {1}
    assert json.loads((tmp_path / "dupes.json").read_text())["2"][0]["id"] == 3
    (jid, values), = db.patched
    assert jid == 4 and values["summary"] == GOOD["summary"] and values["description_trimmed"] is None


def test_company_list_uses_only_known_values():
    tags = config("tags")
    for name, (industry, ctype) in config("company_facts").items():
        assert industry is None or industry in tags["industry"], name
        assert ctype in tags["company_type"], name


def test_fix_company_sets_listed_values_and_keeps_agency_industry():
    facts = {tagging._key("Cushman & Wakefield"): ("real_estate", "mnc"),
             tagging._key("Randstad"): (None, "agency")}
    row = {"industry": "consulting", "company_type": "mnc", "startup_stage": None}
    assert tagging.fix_company(row, "CUSHMAN and Wakefield", facts) == {"industry": "real_estate"}
    row = {"industry": "bfsi", "company_type": "startup", "startup_stage": "early"}
    assert tagging.fix_company(row, "Randstad", facts) == {"company_type": "agency", "startup_stage": None}
    assert row["industry"] == "bfsi"
    assert tagging.fix_company({"industry": "x"}, "Unknown Co", facts) == {}
