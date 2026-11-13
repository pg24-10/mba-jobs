"""Claude's job tags: the fit score is worked out here, from the tags, so it is the same
rule for every job (Phase 3 decision, 14 Nov 2026: Haiku tags, code scores)."""

from .settings import config

OFF_LEVEL = {"entry", "director", "cxo"}      # too junior or beyond most MBA hires
ASKS_MBA = {"required", "preferred"}


def fit_score(tag, tags=None):
    """1-5: start from the function, minus 1 if hands-on, minus 1 if off-level,
    plus 1 if the post asks for an MBA."""
    tags = tags or config("tags")
    score = tags["fit_start"].get(tag.get("function"), 2)
    if tag.get("hands_on"):
        score -= 1
    if tag.get("seniority") in OFF_LEVEL:
        score -= 1
    if tag.get("mba_requirement") in ASKS_MBA:
        score += 1
    return max(1, min(5, score))
