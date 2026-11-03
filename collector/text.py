"""Text helpers shared by every source: matching, names, cities, trimming."""

import re
from functools import lru_cache
import unicodedata

from .settings import config

_WORD = r"[a-z0-9]"


def fold(text):
    """Lower-case, strip accents, unify quotes and dashes, squash spaces."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("‘", "'").replace("\xa0", " ")
    text = re.sub(r"[‐-―]", "-", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def phrase_pattern(phrases):
    """One regex that matches any phrase as whole words ("intern" not in "internal")."""
    parts = sorted({re.escape(fold(p)) for p in phrases if p}, key=len, reverse=True)
    return re.compile(rf"(?<!{_WORD})(?:{'|'.join(parts)})(?!{_WORD})") if parts else None


_exclude = None


def excluded_by(title):
    """Return the exclude phrase that drops this title, or None to keep it."""
    global _exclude
    if _exclude is None:
        _exclude = phrase_pattern(config("filters")["exclude_title"])
    m = _exclude.search(fold(title)) if _exclude else None
    return m.group(0) if m else None


_big_board = None


def big_board_title_ok(title):
    """Workday / Oracle boards list every job a company has; open only titles that
    look like the searches (any search phrase, or a word from big_board_title_words)."""
    global _big_board
    if _big_board is None:
        phrases = [p.strip('"') for g in config("searches")["groups"]
                   for p in re.split(r"\s+OR\s+", g["query"]) if not re.search(r"mba|pgdm", p, re.I)]
        _big_board = phrase_pattern(phrases + config("filters").get("big_board_title_words", []))
    return bool(title) and not excluded_by(title) and bool(_big_board.search(fold(title)))


_agency = None


def looks_like_agency(company, industry=""):
    global _agency
    f = config("filters")
    if _agency is None:
        _agency = phrase_pattern(f["agency_words"])
    if industry and fold(industry) in {fold(i) for i in f.get("agency_industries", [])}:
        return True
    key = company_key(company)
    if any(key == n or key.startswith(n + " ") for n in _agency_names()):
        return True
    return bool(_agency and _agency.search(fold(company)))


@lru_cache
def _agency_names():
    return tuple(company_key(n) for n in config("filters").get("agency_names", []))


def company_key(name):
    """'Novartis Healthcare Pvt. Ltd. India' -> 'novartis healthcare'."""
    text = fold(name)
    text = re.sub(r"\(.*?\)", " ", text)               # (India), (formerly ...)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    words = text.split()
    suffixes = [s.split() for s in config("settings")["company_suffixes"]]
    changed = True
    while changed and words:
        changed = False
        for s in suffixes:
            if len(words) > len(s) and words[-len(s):] == s:
                words = words[: -len(s)]
                changed = True
        if len(words) > 1 and words[-1] == "and":      # "Bain & Company" -> "bain"
            words = words[:-1]
            changed = True
    if len(words) > 1 and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def title_key(title):
    text = fold(title)
    text = re.sub(r"\(.*?\)", " ", text) if len(re.sub(r"\(.*?\)", "", text).strip()) > 3 else text
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return " ".join(text.split())


# --------------------------------------------------------------- cities

_CITY_WORDS = {
    "Bangalore": ["bangalore", "bengaluru", "bangalore urban"],
    "Mumbai": ["mumbai", "navi mumbai", "thane", "bombay"],
    "Delhi NCR": ["delhi", "new delhi", "gurugram", "gurgaon", "noida", "greater noida",
                  "faridabad", "ghaziabad", "manesar", "ncr"],
    "Hyderabad": ["hyderabad", "secunderabad"],
    "Pune": ["pune", "pimpri", "chinchwad"],
    "Chennai": ["chennai", "madras"],
    "Kolkata": ["kolkata", "calcutta"],
}
_city_patterns = {city: phrase_pattern(words) for city, words in _CITY_WORDS.items()}
_REMOTE = phrase_pattern(["remote", "work from home", "wfh"])
_HYBRID = phrase_pattern(["hybrid"])


def city_of(location):
    """Map any location text to one of the site's cities, or the raw first part."""
    text = fold(location)
    for city, pattern in _city_patterns.items():
        if pattern.search(text):
            return city
    if _REMOTE.search(text):
        return "Remote (India)"
    first = (location or "").split(",")[0].strip()
    return first or None


_STATES = phrase_pattern([
    "india", "karnataka", "maharashtra", "delhi", "haryana", "uttar pradesh", "telangana",
    "tamil nadu", "west bengal", "gujarat", "rajasthan", "kerala", "andhra pradesh", "punjab",
    "madhya pradesh", "odisha", "bihar", "assam", "goa", "chandigarh", "jharkhand",
    "uttarakhand", "himachal pradesh", "chhattisgarh", "jammu and kashmir", "apac", "asia",
    "ka", "mh", "dl", "hr", "up", "tn", "ts", "tg", "wb", "gj", "rj", "kl", "ap",  # short forms
])


def is_vague(location):
    """True when a location names no city: '', 'India', 'Karnataka, India', 'APAC'."""
    first = fold((location or "").split(",")[0])
    first = re.sub(r"\b(area|region)\b", "", first).strip()
    return not first or bool(_STATES.fullmatch(first))


def work_mode_of(*texts):
    blob = " ".join(fold(t) for t in texts if t)
    if _REMOTE.search(blob):
        return "remote"
    if _HYBRID.search(blob):
        return "hybrid"
    return None


# --------------------------------------------------------------- descriptions

_REQ_HEADINGS = [
    "requirements", "requirement", "qualifications", "qualification", "eligibility",
    "what you'll need", "what you will need", "what you need", "what we're looking for",
    "what we are looking for", "who you are", "who we are looking for", "about you",
    "desired profile", "desired candidate profile", "candidate profile", "skills required",
    "required skills", "key skills", "must have", "must-have", "experience required",
    "education", "you should have", "you have", "you bring", "what you bring",
    "ideal candidate", "the ideal candidate", "basic qualifications", "preferred qualifications",
    "minimum qualifications", "skills and experience", "experience and skills",
    "skills & experience", "experience & skills", "your profile",
]
_req = phrase_pattern(_REQ_HEADINGS)


_ROLE_HEADINGS = [
    "about the role", "the role", "role overview", "role summary", "job summary",
    "position summary", "job purpose", "the opportunity", "your role", "job description",
    "key responsibilities", "responsibilities", "what you'll do", "what you will do",
    "what you'll be doing", "what you will be doing", "your responsibilities",
]
_role = phrase_pattern(_ROLE_HEADINGS)


def trim_requirements(description, limit=None):
    """The part of a description Claude needs: a short "about the role" piece,
    then the requirements, up to `limit` characters in all. Company intros are
    skipped when a heading shows where the role starts."""
    s = config("settings")
    limit = limit or s["description_chars"]
    role_limit = min(s.get("role_chars", 1000), limit)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", description or "")).strip()
    if not text:
        return None
    folded = fold(text)
    role = _role.search(folded)
    req = _req.search(folded, role.end() if role else 0)
    start = role.start() if role else 0
    # only trust a requirements heading found after the first few lines of intro
    if not req or req.start() <= start + 80:
        return text[start:start + limit]
    about = text[start:req.start()].strip()[:role_limit]
    needs = text[req.start():]
    return (about + " ... " + needs)[:limit] if about else needs[:limit]


_EXP = re.compile(r"(\d{1,2})\s*(?:-|to|–)\s*(\d{1,2})\s*(?:yrs?|years?)", re.I)


def experience_range(text):
    """'5-10 Yrs' -> (5, 10)."""
    m = _EXP.search(text or "")
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def to_lpa(amount, interval="yearly", currency="INR"):
    """Convert a salary figure to lakhs per annum (INR only)."""
    if amount is None or (currency and currency.upper() not in ("INR", "RS", "₹")):
        return None
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None
    if amount != amount or amount <= 0:   # NaN
        return None
    per_year = {"yearly": 1, "monthly": 12, "weekly": 52, "daily": 260, "hourly": 2080}.get(
        (interval or "yearly").lower(), 1)
    return round(amount * per_year / 100000, 1)
