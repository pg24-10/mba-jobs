from collector.text import city_of, company_key, excluded_by, experience_range, to_lpa


def test_intern_is_whole_word():
    assert excluded_by("Summer Intern - Marketing") == "summer intern"
    assert excluded_by("Product Intern") == "intern"
    assert excluded_by("International Business Manager") is None
    assert excluded_by("Internal Audit Manager") is None
    assert excluded_by("Management Trainee - Internal Audit, Risk & Compliance") is None


def test_obvious_excludes():
    assert excluded_by("Senior Software Engineer, Payments") == "software engineer"
    assert excluded_by("Telecaller (Hindi)") == "telecaller"
    assert excluded_by(".NET Developer") in (".net", "developer")


def test_company_key():
    assert company_key("Novartis Healthcare Pvt. Ltd. India") == "novartis healthcare"
    assert company_key("Purplle (Manash Lifestyle Private Limited)") == "purplle"
    assert company_key("UBS Business Solutions (India) Private Limited") == "ubs business solutions"
    assert company_key("Bain & Company, Inc.") == "bain"
    assert company_key("Bain and Company India Pvt. Ltd.") == "bain"
    assert company_key("Siemens AG") == "siemens"
    assert company_key("Hindustan Unilever Ltd") == "hindustan unilever"


def test_city():
    assert city_of("Gurugram, Haryana, India") == "Delhi NCR"
    assert city_of("Greater Delhi Area") == "Delhi NCR"
    assert city_of("Bangalore Urban, Karnataka, India") == "Bangalore"
    assert city_of("Mumbai Metropolitan Region") == "Mumbai"
    assert city_of("Pune/Pimpri-Chinchwad Area") == "Pune"
    assert city_of("Ahmedabad, Gujarat, India") == "Ahmedabad"


def test_experience_and_salary():
    assert experience_range("5-10 Yrs") == (5, 10)
    assert experience_range("2 to 4 years") == (2, 4)
    assert to_lpa(1800000) == 18.0
    assert to_lpa(150000, "monthly") == 18.0
    assert to_lpa(100000, "yearly", "USD") is None
