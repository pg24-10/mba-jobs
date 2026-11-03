"""Safety test: the exclude filter must keep every real campus role.

If you add an exclude word and this fails, the word would have hidden a job
ISB students actually applied to. Remove or narrow the word.

Reads reference/campus_roles.xlsx, which stays on the Mac (ISB data is never
committed), so on GitHub this test is skipped.
"""

import openpyxl
import pytest

from collector.settings import REFERENCE
from collector.text import excluded_by

FILE = REFERENCE / "campus_roles.xlsx"


def _roles():
    if not FILE.exists():
        return []
    rows = list(openpyxl.load_workbook(FILE, read_only=True).active.iter_rows(values_only=True))
    cols = [str(c).strip() if c else "" for c in rows[0]]
    ci, ti = cols.index("Company Name"), cols.index("Job Title")
    return [{"company": str(r[ci]), "title": str(r[ti])} for r in rows[1:] if r[ti]]


ROLES = _roles()
needs_file = pytest.mark.skipif(not ROLES, reason="reference/campus_roles.xlsx is only on the Mac")


@needs_file
def test_file_has_all_roles():
    assert len(ROLES) == 125


@needs_file
@pytest.mark.parametrize("role", ROLES, ids=lambda r: f"{r['company'][:25]} | {r['title'][:40]}")
def test_campus_role_is_kept(role):
    hit = excluded_by(role["title"])
    assert hit is None, f"'{role['title']}' would be dropped by the exclude word '{hit}'"
