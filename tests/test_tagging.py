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

from collector import tagging
from collector.tagging import check, copied

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
    assert row["experience_min"] == 4.0


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


def test_parts_export_and_import(tmp_path, monkeypatch):
    monkeypatch.setattr(tagging, "DIR", tmp_path)
    monkeypatch.setattr(tagging, "FAILED", tmp_path / "failed.json")
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
    """Hands out untagged jobs like Supabase: flagged ones drop out of later pages."""
    base = "x"

    def __init__(self, jobs):
        self.jobs, self.flagged = jobs, set()

    def _send(self, method, url, params=None, headers=None, data=None, timeout=None):
        if method == "PATCH":
            self.flagged |= {int(i) for i in params["id"][4:-1].split(",")}
            return None
        start, end = map(int, headers["Range"].split("-"))
        left = [j for j in self.jobs if j["id"] not in self.flagged]
        return left[start:end + 1]


def test_export_leaves_out_and_flags_thin_posts(tmp_path, monkeypatch):
    monkeypatch.setattr(tagging, "FAILED", tmp_path / "failed.json")
    long, short = " ".join(["word"] * 80), "Hiring a manager. Apply now."
    jobs = [{"id": i, "title": "PM", "company": "X", "location_city": "Pune",
             "description_trimmed": short if i % 2 else long} for i in range(1, 9)]
    db = PagingDB(jobs)
    assert tagging.export(db, 3, tmp_path / "b.json", log=lambda m: None) == 3
    assert [j["id"] for j in json.loads((tmp_path / "b.json").read_text())] == [2, 4, 6]
    assert db.flagged == {1, 3, 5}
