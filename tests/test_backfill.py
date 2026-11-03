from collector import backfill as bf

GROUPS = [{"id": "product", "query": "x"}, {"id": "strategy", "query": "y"}]
CITIES = [{"name": "Bangalore"}, {"name": "Mumbai"}]


def test_steps_order_and_count():
    st = bf.steps(["linkedin", "iimjobs", "ats"], GROUPS, CITIES)
    assert [s[1] for s in st] == ["iimjobs", "iimjobs"] + ["linkedin"] * 4 + ["ats"]
    assert st[-2][0] == "linkedin|strategy|Mumbai"


def test_resumes_and_pauses_linkedin(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "STATE", tmp_path)
    monkeypatch.setattr(bf, "CHECKPOINT", tmp_path / "backfill.json")
    monkeypatch.setattr(bf, "load_isb", lambda db: None)
    calls = []

    def fake_run(blocked):
        def _run(db, sources, groups, locations, since, isb, log):
            calls.append(sources[0])
            status = "pending" if blocked and sources == ["linkedin"] else "success"
            return {sources[0]: {"status": status, "new": 1}}
        return _run

    quiet = lambda *a: None
    monkeypatch.setattr(bf, "run", fake_run(blocked=True))
    assert not bf.backfill(None, ["naukri", "linkedin"], GROUPS, CITIES, log=quiet)
    assert calls == ["naukri"] * 4 + ["linkedin"]      # LinkedIn stops after one push-back

    calls.clear()
    monkeypatch.setattr(bf, "run", fake_run(blocked=False))
    assert bf.backfill(None, ["naukri", "linkedin"], GROUPS, CITIES, log=quiet)
    assert calls == ["linkedin"] * 4                    # only the unfinished steps
