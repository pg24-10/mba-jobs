"""Cards first, Claude sorts, then only the chosen job pages are opened."""

import csv

import pytest

from collector import pipeline, triage


@pytest.fixture
def tri(tmp_path, monkeypatch):
    monkeypatch.setattr(triage, "DIR", tmp_path)
    monkeypatch.setattr(triage, "QUEUE", tmp_path / "queue.jsonl")
    monkeypatch.setattr(triage, "DECISIONS", tmp_path / "decisions.json")
    return tmp_path


class _DB:
    def known_source_ids(self, ids):
        return set()

    def described_keys(self, keys):
        return set()


CARDS = [(1, "Product Manager"), (2, "Java Developer"), (3, "Strategy Manager")]


class _LI:
    requests = blocks = 0
    opened = []

    def __init__(self, log=None):
        pass

    def search(self, *a, **k):
        yield from ({"id": str(i), "title": t, "company": "Acme", "location": "Bengaluru, Karnataka, India",
                     "posted": "2026-11-01"} for i, t in CARDS)

    def detail(self, i):
        _LI.opened.append(i)
        return {"description": f"about job {i}"}


def test_backfill_saves_cards_and_queues_without_opening(tri, monkeypatch):
    _LI.opened = []
    monkeypatch.setattr(pipeline, "LinkedIn", _LI)
    groups = [{"id": "product", "query": '"product manager"'}]
    locs = [{"name": "Bangalore", "linkedin": "Bengaluru"}]
    raws = pipeline.collect_linkedin(_DB(), groups, locs, pipeline.now() - pipeline.timedelta(days=1),
                                     log=lambda *a: None, details=False)
    assert _LI.opened == []                                    # no job pages
    assert {r["source_id"] for r in raws} == {"linkedin:1", "linkedin:3"}   # Java Developer filtered out
    assert all(r["description"] is None for r in raws)
    assert set(triage.load_queue()) == {"1", "3"}


def test_export_import_and_fill(tri, monkeypatch):
    triage.queue_cards([{"id": "1", "title": "Product Manager", "company": "Acme",
                         "location": "Bengaluru, Karnataka, India", "search_city": "Bangalore"},
                        {"id": "3", "title": "Sales Executive", "company": "Acme",
                         "location": "Bengaluru, Karnataka, India", "search_city": "Bangalore"}])
    out = tri / "to-sort.csv"
    assert triage.export(out) == 2
    rows = list(csv.DictReader(open(out)))
    for r in rows:
        r["decision"], r["reason"] = ("open", "PM role") if r["id"] == "1" else ("skip", "too junior")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows + [{**rows[0], "id": "999", "decision": "open"}])
    saved, problems = triage.import_decisions(out)
    assert saved == 2 and len(problems) == 1                  # unknown id flagged, not saved
    assert triage.export(out) == 0                            # nothing left to sort

    _LI.opened = []
    saved_rows = []
    monkeypatch.setattr("collector.sources.linkedin.LinkedIn", _LI)
    monkeypatch.setattr(pipeline, "load_isb", lambda db: pipeline.IsbMatcher([]))
    monkeypatch.setattr(pipeline, "save", lambda db, rows, src, log:
                        saved_rows.extend(rows) or [{"dedupe_key": r["dedupe_key"], "id": 7, "is_new": False}
                                                    for r in rows])
    monkeypatch.setattr(pipeline, "write_inbox", lambda items: None)
    result = triage.fill_details(None, log=lambda *a: None)
    assert _LI.opened == ["1"] and result["opened"] == 1      # only the "open" one
    assert saved_rows[0]["description_trimmed"]
    assert triage.status()["filled"] == 1
    assert triage.fill_details(None, log=lambda *a: None)["opened"] == 0   # not opened twice


def test_fill_stops_on_block_and_keeps_what_it_opened(tri, monkeypatch):
    triage.queue_cards([{"id": str(i), "title": "Product Manager", "company": f"Co{i}",
                         "location": "Bengaluru, Karnataka, India", "search_city": "Bangalore"} for i in (1, 2)])
    triage.update_decisions({"1": {"decision": "open"}, "2": {"decision": "open"}})

    class Blocky(_LI):
        def detail(self, i):
            if i == "2":
                raise pipeline.Blocked("429")
            return {"description": "d"}
    monkeypatch.setattr("collector.sources.linkedin.LinkedIn", Blocky)
    monkeypatch.setattr(pipeline, "load_isb", lambda db: pipeline.IsbMatcher([]))
    monkeypatch.setattr(pipeline, "save", lambda db, rows, src, log: [])
    monkeypatch.setattr(pipeline, "write_inbox", lambda items: None)
    result = triage.fill_details(None, log=lambda *a: None)
    assert result["opened"] == 1 and result["stopped"]
    d = triage.load_decisions()
    assert d["1"].get("filled") and not d["2"].get("filled")


def test_auto_runs_steps_then_waits_for_claude_then_fills(tri, monkeypatch):
    from collector import auto
    sessions, sleeps, fills = [True], [], []
    monkeypatch.setattr(auto, "backfill", lambda *a, **k: (sessions.append(1) or len(sessions) > 2))
    triage.queue_cards([{"id": "1", "title": "Product Manager", "company": "Acme"}])

    def claude_sorts(seconds):                      # while auto waits, Claude sorts the card
        sleeps.append(seconds)
        if seconds == auto.SORT_WAIT:
            triage.update_decisions({"1": {"decision": "open"}})

    def fill(db, log=print):
        fills.append(1)
        triage.update_decisions({"1": {"filled": "now"}})
        return {"opened": 1, "left": 0, "stopped": None}
    monkeypatch.setattr(triage, "fill_details", fill)
    assert auto.run_auto(None, log=lambda *a: None, sleep=claude_sorts)
    assert sleeps == [auto.SESSION_REST, auto.SORT_WAIT]    # one paused session, one wait for Claude
    assert fills == [1]


def test_auto_gives_up_waiting_when_nobody_sorts(tri, monkeypatch):
    from collector import auto
    monkeypatch.setattr(auto, "backfill", lambda *a, **k: True)
    triage.queue_cards([{"id": "1", "title": "Product Manager", "company": "Acme"}])
    assert auto.run_auto(None, log=lambda *a: None, sleep=lambda s: None) is False
