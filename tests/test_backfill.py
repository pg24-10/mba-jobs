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


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "STATE", tmp_path)
    monkeypatch.setattr(bf, "CHECKPOINT", tmp_path / "backfill.json")
    monkeypatch.setattr(bf, "load_isb", lambda db: None)


def test_waits_for_internet_and_retries_the_step(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    net = {"up": False}
    calls = []

    def _run(db, sources, groups, locations, since, isb, log):
        calls.append(sources[0])
        return {sources[0]: {"status": "success" if net["up"] else "failed", "new": 0}}

    def _wait(log, sleep=None):
        net["up"] = True                                 # the Wi-Fi comes back
    monkeypatch.setattr(bf, "run", _run)
    monkeypatch.setattr(bf, "online", lambda: net["up"])
    monkeypatch.setattr(bf, "wait_for_internet", _wait)
    assert bf.backfill(None, ["iimjobs"], GROUPS, CITIES, log=lambda *a: None)
    assert calls == ["iimjobs"] * 3                      # first step tried twice, second once


def test_pauses_a_source_that_keeps_failing_online(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    calls = []

    def _run(db, sources, groups, locations, since, isb, log):
        calls.append(sources[0])
        return {sources[0]: {"status": "failed" if sources == ["naukri"] else "success", "new": 0}}
    monkeypatch.setattr(bf, "run", _run)
    monkeypatch.setattr(bf, "online", lambda: True)
    groups = GROUPS + [{"id": "growth", "query": "z"}]
    assert not bf.backfill(None, ["naukri", "linkedin"], groups, CITIES, log=lambda *a: None)
    assert calls == ["naukri"] * 3 + ["linkedin"] * 6    # Naukri stops after 3 failures; LinkedIn still runs


def test_wait_for_internet_checks_until_back(monkeypatch):
    checks = iter([False, False, True])
    monkeypatch.setattr(bf, "online", lambda: next(checks))
    naps = []
    bf.wait_for_internet(lambda *a: None, sleep=naps.append)
    assert naps == [bf.CHECK_EVERY] * 2


def test_checkpoint_keeps_steps_from_another_window(tmp_path, monkeypatch):
    from collector import backfill
    monkeypatch.setattr(backfill, "STATE", tmp_path)
    monkeypatch.setattr(backfill, "CHECKPOINT", tmp_path / "backfill.json")
    mine = {"since": "2026-10-04T20:44:00+00:00", "done": ["a"], "seconds": {}}
    other = {"since": mine["since"], "done": ["a", "naukri|x|y"], "seconds": {"naukri": [60]}}
    backfill.save_checkpoint(other)
    backfill.save_checkpoint(mine)
    import json
    disk = json.loads((tmp_path / "backfill.json").read_text())
    assert disk["done"] == ["a", "naukri|x|y"] and disk["seconds"] == {"naukri": [60]}
