"""A network drop must never look like "no more results" (that marked steps done with 0 jobs)."""

import pytest
import requests

from collector.sources import NetworkDown
from collector.sources import linkedin as li_mod


class _Resp:
    status_code, url, text = 200, "https://www.linkedin.com/x", "<li>ok</li>"


def _client(monkeypatch, answers, up):
    monkeypatch.setattr(li_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(li_mod, "online", lambda: up["now"])
    li = li_mod.LinkedIn(log=lambda *a: None)
    li.rest_every = 0

    def get(url, params=None, timeout=None):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a
    li.http.get = get
    return li


def test_waits_out_a_drop_and_carries_on(monkeypatch):
    up = {"now": False}
    def back(limit, log=None):
        up["now"] = True
        return True
    monkeypatch.setattr(li_mod, "wait_until_online", back)
    err = requests.ConnectionError("Failed to resolve")
    li = _client(monkeypatch, [err, _Resp()], up)
    assert li._get("u") == "<li>ok</li>"


def test_internet_stays_down_fails_the_step(monkeypatch):
    monkeypatch.setattr(li_mod, "wait_until_online", lambda limit, log=None: False)
    li = _client(monkeypatch, [requests.ConnectionError("Failed to resolve")], {"now": False})
    with pytest.raises(NetworkDown):
        li._get("u")


def test_linkedin_not_answering_fails_the_step(monkeypatch):
    t = requests.ReadTimeout("Read timed out")
    li = _client(monkeypatch, [t, t, t], {"now": True})
    with pytest.raises(NetworkDown):
        li._get("u")


def test_database_waits_out_a_drop(monkeypatch):
    from collector import db as db_mod
    calls, up = [], {"now": False}
    class S:
        def request(self, method, url, **kw):
            calls.append(1)
            if not up["now"]:
                raise requests.ConnectionError("Failed to resolve")
            return type("R", (), {"status_code": 200, "text": "", "json": lambda self: None})()
    def back(limit, log=None):
        up["now"] = True
        return True
    monkeypatch.setattr(db_mod, "online", lambda: up["now"])
    monkeypatch.setattr(db_mod, "wait_until_online", back)
    monkeypatch.setattr(db_mod.time, "sleep", lambda s: pytest.fail("should not use up a retry"))
    d = db_mod.DB.__new__(db_mod.DB)
    d.s = S()
    assert d._send("GET", "u") is None and len(calls) == 2
