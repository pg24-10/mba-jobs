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
