"""Small Supabase client over its REST API (service key: read and write)."""

import json
import time

import requests

from .settings import secret

try:
    import certifi
    _VERIFY = certifi.where()
except ImportError:
    _VERIFY = True


class DB:
    def __init__(self):
        url = secret("SUPABASE_URL").rstrip("/")
        url = url[: -len("/rest/v1")] if url.endswith("/rest/v1") else url   # either form works
        self.base = url + "/rest/v1"
        key = secret("SUPABASE_SERVICE_KEY")
        self.s = requests.Session()
        self.s.verify = _VERIFY
        self.s.headers.update({
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })

    WAITS = [5, 15, 30, 60, 120]        # about 4 minutes in all: rides out a Wi-Fi drop

    def _send(self, method, url, **kw):
        """One request, retried on network errors and 5xx."""
        for attempt, wait in enumerate(self.WAITS + [None]):
            try:
                r = self.s.request(method, url, **kw)
                if r.status_code < 500 or wait is None:
                    return self._check(r)
            except requests.RequestException:
                if wait is None:
                    raise
            time.sleep(wait)

    def _check(self, r):
        if r.status_code >= 400:
            raise RuntimeError(f"Supabase {r.request.method} {r.url.split('?')[0]} -> {r.status_code}: {r.text[:500]}")
        return r.json() if r.text else None

    def rpc(self, fn, **args):
        return self._send("POST", f"{self.base}/rpc/{fn}", data=json.dumps(args, default=str), timeout=120)

    def select(self, table, params=None):
        """Read all matching rows, 1,000 at a time."""
        out, start = [], 0
        while True:
            rows = self._send("GET", f"{self.base}/{table}", params=params or {},
                              headers={"Range": f"{start}-{start + 999}"}, timeout=60)
            out += rows
            if len(rows) < 1000:
                return out
            start += 1000

    def insert(self, table, row):
        return self._send("POST", f"{self.base}/{table}", data=json.dumps(row, default=str),
                          headers={"Prefer": "return=representation"}, timeout=60)[0]

    def update(self, table, match, values):
        params = {k: f"eq.{v}" for k, v in match.items()}
        return self._send("PATCH", f"{self.base}/{table}", params=params,
                          data=json.dumps(values, default=str), timeout=60)

    def upsert(self, table, rows, on_conflict):
        for i in range(0, len(rows), 500):
            self._send("POST", f"{self.base}/{table}", params={"on_conflict": on_conflict},
                       data=json.dumps(rows[i:i + 500], default=str),
                       headers={"Prefer": "resolution=merge-duplicates,return=minimal"}, timeout=120)

    def upsert_jobs(self, rows):
        out = []
        for i in range(0, len(rows), 200):
            out += self.rpc("upsert_jobs", rows=rows[i:i + 200])
        return out

    def known_source_ids(self, ids):
        found = set()
        ids = list(ids)
        for i in range(0, len(ids), 500):
            found |= set(self.rpc("known_source_ids", ids=ids[i:i + 500]) or [])
        return found
