"""The role/level rules, pinned against real-style titles.

Each row: (title, expected family key or None, expected level or None).
None/None means the role must NOT be listed.
"""
import pytest

from intern_engine import roles
from intern_engine.roles import COOP, ENTRY, INTERN, NEW_GRAD, UNCLEAR

CASES = [
    # --- internships / co-ops ------------------------------------------------
    ("Product Marketing Intern, Summer 2027", "product_marketing", INTERN),
    ("GTM Engineer Intern", "gtm_engineering", INTERN),
    ("Growth Marketing Intern", "growth_marketing", INTERN),
    ("Lead Generation Intern", "growth_marketing", INTERN),  # "lead" is the job, not seniority
    ("Demand Generation Intern", "growth_marketing", INTERN),
    ("Marketing Co-op (Winter 2027)", "marketing", COOP),
    ("Sales Development Intern", "sales", INTERN),
    ("Intern, Go-to-Market Strategy", "gtm_growth", INTERN),
    ("Growth Intern", "gtm_growth", INTERN),
    ("Business Development Co-op", "sales", COOP),
    ("Marketing Intern - Lead Gen", "growth_marketing", INTERN),
    ("Revenue Operations Intern", "gtm_growth", INTERN),
    ("Internship Program Manager, Marketing", None, None),
    ("Software Engineer Intern", None, None),
    ("Intern, Finance", None, None),
    ("AI Product Management Intern", None, None),
    ("Product Design Intern, Growth", None, None),
    ("Marketing Design Intern", None, None),
    # --- new grad --------------------------------------------------------------
    ("New Grad Account Executive", "sales", NEW_GRAD),
    ("Growth Marketing Associate, New Grad 2027", "growth_marketing", NEW_GRAD),
    ("Early Career Sales Program", "sales", NEW_GRAD),
    ("Graduate Sales Associate", "sales", NEW_GRAD),
    ("Graduate Nurse", None, None),
    ("University Graduate - Product Marketing", "product_marketing", NEW_GRAD),
    ("Rotational Program, Go-to-Market", "gtm_growth", NEW_GRAD),
    ("Early Career Software Engineer", None, None),
    # --- entry level (stated in the title) ---------------------------------------
    ("Associate Product Marketing Manager", "product_marketing", ENTRY),
    ("Junior Account Executive", "sales", ENTRY),
    ("Sales Development Representative", "sales", ENTRY),
    ("Business Development Representative - French Speaking", "sales", ENTRY),
    ("Enterprise Sales Development Representative", "sales", ENTRY),
    ("SDR", "sales", ENTRY),
    ("Sales Development - Canada", "sales", ENTRY),
    ("Growth Marketing, Associate", "growth_marketing", ENTRY),
    ("GTM Associate, Data Partnerships", None, None),   # partnerships = adjacent
    ("GTM Associate", "gtm_growth", ENTRY),
    ("Marketing Coordinator", "marketing", ENTRY),
    ("Account Executive I", "sales", ENTRY),
    ("Junior GTM Engineer", "gtm_engineering", ENTRY),
    ("Associate, Growth", "gtm_growth", ENTRY),
    ("Sales Associate", "sales", ENTRY),
    ("Marketing Assistant", "marketing", ENTRY),
    # --- no level stated -------------------------------------------------------
    ("GTM Engineer", "gtm_engineering", UNCLEAR),
    ("Account Executive", "sales", UNCLEAR),
    ("Growth Marketer", "growth_marketing", UNCLEAR),
    ("GTM Engineer - Systems and Infrastructure", "gtm_engineering", UNCLEAR),
    ("Website Growth Engineer", "gtm_engineering", UNCLEAR),
    ("Software Engineer, GTM Ops", "gtm_engineering", UNCLEAR),
    ("Marketing Engineering Intern", "gtm_engineering", INTERN),
    ("Software Engineer, Growth", "gtm_engineering", UNCLEAR),
    ("Product Marketing, GTM", "product_marketing", UNCLEAR),
    ("Account Manager - Corporate", "sales", UNCLEAR),
    ("B2B Marketing - Nordics", "marketing", UNCLEAR),
    # --- senior / out of scope: must be dropped ----------------------------------
    ("Product Marketing Manager", None, None),
    ("Senior Product Marketing Manager", None, None),
    ("Product Marketing Lead", None, None),
    ("Head of Marketing", None, None),
    ("Senior Account Executive", None, None),
    ("Strategic Account Executive - Germany", None, None),
    ("Enterprise Account Executive", None, None),
    ("Account Executive, Mid-Market - East", None, None),
    ("Sales Development Lead - United States", None, None),
    ("Sales Manager, Enterprise", None, None),
    ("VP Sales, EMEA", None, None),
    ("Sales Development Manager | Housing", None, None),
    ("Associate Marketing Manager", "marketing", ENTRY),
    ("Senior Associate, Growth Marketing", None, None),
    ("Associate Director, Product Marketing", None, None),
    ("Account Executive II", None, None),
    ("Founding Account Executive", None, None),
    ("Growth Lead", None, None),
    ("GTM Engineer Manager - Seller Efficiency", None, None),
    ("Staff Growth Engineer", None, None),
    ("GTM Recruiter", None, None),
    ("Commercial Counsel", None, None),
    ("Sales Finance", None, None),
    ("Growth PM", None, None),
    ("Sales Manager_Chinese Vertical", None, None),
    ("Seasonal Sales Associate - La Cantera", None, None),
    ("Leasing & Sales Consultant- The Landing", None, None),
    ("Sales Commission Analyst", None, None),
    ("Technical Account Manager", None, None),
    ("Software Engineer, Provider Growth", None, None),
    ("Data Scientist, Growth", None, None),
    ("Product Owner, Growth", None, None),
    ("Product Designer, Growth", None, None),
    ("Solutions Engineer", None, None),
    ("Sales Engineer", None, None),
    ("Customer Success Manager", None, None),
    ("Forward Deployed Engineer, Agentic Platform", None, None),
    ("Software Engineer", None, None),
    ("Executive Assistant - Revenue", None, None),
    ("Partner Development Manager - AWS", None, None),
]


@pytest.mark.parametrize("title,family,level", CASES)
def test_title(title, family, level):
    v = roles.classify(title)
    if family is None:
        assert not v.keep, f"{title!r} should be dropped, got {v}"
    else:
        assert v.keep, f"{title!r} should be kept, got {v}"
        assert (v.family, v.level) == (family, level)


def test_experience_decides_unleveled_titles():
    assert roles.classify("Account Executive", "You have 5+ years of experience closing.").keep is False
    v = roles.classify("Account Executive", "0-2 years of experience in sales.")
    assert v.keep and v.level == ENTRY
    assert roles.classify("Product Marketing Manager", "1+ years of experience in marketing.").keep is False
    assert roles.classify("Manager, Sales Development", "1+ years of experience managing.").keep is False
    assert roles.classify("Associate Manager, Product Marketing", "5+ years of experience.").keep is False
    assert roles.classify("Associate Manager, Product Marketing", "2+ years of experience.").keep is True
    assert roles.classify("Product Marketing Manager", "").keep is False


def test_board_job_type_marks_an_internship():
    v = roles.classify("Marketing, Summer 2027", employment_type="Intern")
    assert v.keep and v.level == INTERN


def test_min_years():
    assert roles.min_years("We need 3+ years of experience and 5 years in SaaS.") == 5
    assert roles.min_years("Founded 25 years ago.") is None
    assert roles.min_years("") is None
