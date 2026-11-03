"""Company lists: placement lineup, past ISB recruiters, watch list.

Also the "Past ISB recruiter" fuzzy match. Matches below the accept score but
above the review score are written to data/logs/isb_review.csv for a human to
check; they are not tagged.
"""

import csv
from functools import lru_cache

import openpyxl
from rapidfuzz import fuzz, process

from .settings import LOGS, REFERENCE, config
from .text import company_key


def _lineup_file():
    files = sorted(REFERENCE.glob("PGP - Final Placements*.xlsx"))
    if not files:
        raise SystemExit("Placement lineup spreadsheet not found in reference/")
    return files[0]


def lineup():
    """[(name, industry)] from all Cluster sheets (headers on row 4)."""
    out = []
    wb = openpyxl.load_workbook(_lineup_file(), read_only=True)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        header = next((i for i, r in enumerate(rows) if "Company Name" in [str(c).strip() if c else "" for c in r]), None)
        if header is None:
            continue
        cols = [str(c).strip() if c else "" for c in rows[header]]
        ci, ii = cols.index("Company Name"), cols.index("Industry")
        for r in rows[header + 1:]:
            if r[ci] and str(r[ci]).strip():
                out.append((str(r[ci]).strip(), (str(r[ii]).strip() if r[ii] else None)))
    return out


def isb_recruiters():
    ws = openpyxl.load_workbook(REFERENCE / "ISB_Recruiter_Names.xlsx", read_only=True).active
    return [str(r[1]).strip() for r in list(ws.iter_rows(values_only=True))[1:] if r[1] and str(r[1]).strip()]


def watch_list():
    return config("companies_watch")["companies"] or []


def build_companies():
    """All companies as rows for the `companies` table, keyed by company_key."""
    rows = {}

    def add(name, **flags):
        key = company_key(name)
        if not key:
            return
        row = rows.setdefault(key, {"name": name, "company_key": key, "in_lineup": False,
                                    "in_isb_recruiters": False, "in_watch_list": False,
                                    "lineup_industry": None})
        for k, v in flags.items():
            row[k] = row[k] or v

    for name, industry in lineup():
        add(name, in_lineup=True, lineup_industry=industry)
    for name in watch_list():
        add(name, in_watch_list=True)
    for name in isb_recruiters():
        add(name, in_isb_recruiters=True)
    # lineup / watch companies that are past recruiters under a slightly different name
    matcher = IsbMatcher()
    for row in rows.values():
        if not row["in_isb_recruiters"] and matcher.match(row["name"]):
            row["in_isb_recruiters"] = True
    return list(rows.values())


class IsbMatcher:
    def __init__(self, names=None):
        names = names if names is not None else isb_recruiters()
        self.keys = sorted({company_key(n) for n in names if company_key(n)})
        self.keyset = set(self.keys)
        s = config("settings")["isb_match"]
        self.accept, self.review = s["accept"], s["review"]
        self.to_review = {}
        aliases = (config("isb_aliases") or {}).get("aliases") or {}
        self.aliases = {company_key(k): company_key(v) for k, v in aliases.items()}

    def match(self, company):
        """True when the company is a past ISB recruiter (confident match only)."""
        return self.which(company) is not None

    @lru_cache(maxsize=20000)
    def which(self, company):
        """The ISB recruiter key this company matches (confident match only), or None."""
        key = company_key(company)
        if not key:
            return None
        if key in self.keyset:
            return key
        if self.aliases.get(key) in self.keyset:
            return self.aliases[key]
        # "amazon development centre" is Amazon: an ISB name that is the first
        # whole word(s) of this company's name, at least 3 letters ("ubs", "dsp").
        words = key.split()
        for n in range(len(words) - 1, 0, -1):
            prefix = " ".join(words[:n])
            if prefix in self.keyset and len(prefix) >= 3:
                self._log(company, prefix, 100, "prefix: accepted")
                return prefix
        # The other way round ("exl" vs ISB "exl service") is often a different
        # company ("jsw paints" vs "jsw group"): log it, do not tag.
        longer = next((k for k in self.keys if k.startswith(key + " ")), None)
        if longer:
            self._log(company, longer, 100, "ISB name is longer: NOT tagged, please check")
            return None
        best = process.extractOne(key, self.keys, scorer=fuzz.ratio)
        if best and best[1] >= self.accept:
            self._log(company, best[0], round(best[1]), "fuzzy: accepted")
            return best[0]
        if best and best[1] >= self.review:
            self._log(company, best[0], round(best[1]), "fuzzy: NOT tagged, please check")
        return None

    def _log(self, company, matched, score, note):
        self.to_review[company] = (matched, score, note)

    def write_review_log(self, name="isb_review.csv"):
        if not self.to_review:
            return None
        LOGS.mkdir(parents=True, exist_ok=True)
        path = LOGS / name
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["company_seen", "closest_isb_recruiter_key", "score", "decision"])
            for company, (matched, score, note) in sorted(self.to_review.items()):
                w.writerow([company, matched, score, note])
        return path
