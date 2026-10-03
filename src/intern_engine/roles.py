"""Role-family and level classification for go-to-market roles.

The rules live in ``data/roles.json`` so they can be tuned without touching
code. This module only applies them:

  classify(title, description="", employment_type="") -> Verdict

A role is LISTED when it has a family (product marketing, growth marketing,
GTM engineering, GTM & growth, sales, marketing) AND an early-career level:

  Internship / Co-op   the title (or the board's own job type) says so
  New grad             "new grad", "early career", "graduate program", ...
  Entry level          junior / associate / coordinator / SDR / BDR / "I", or
                       the posting text asks for at most N years' experience
  Level unclear        nothing in the title or text says either way. Kept in
                       its own bucket, never mixed with the stated levels.

Anything with a senior marker (senior, lead, director, head, staff, ...) is
dropped. "Manager", "Enterprise", "Strategic" are softer: an explicit entry
marker or a low experience requirement can still rescue the role
("Associate Product Marketing Manager"), otherwise it is dropped.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache

from . import paths

ROLES_PATH = os.path.join(os.path.dirname(paths.CONFIG_PATH), "roles.json")

INTERN = "Internship"
COOP = "Co-op"
NEW_GRAD = "New grad"
ENTRY = "Entry level"
UNCLEAR = "Level unclear"
LEVELS = (INTERN, COOP, NEW_GRAD, ENTRY, UNCLEAR)

_COOP_RE = re.compile(r"\bco[\s-]?op\b|cooperative education", re.IGNORECASE)

# "3+ years of experience", "2-4 years' experience", "minimum 5 yrs ... experience"
_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|\s*(?:-|–|—|to)\s*\d{1,2})?\s*\+?\s*(?:years?|yrs?)"
    r"(?=[^.\n]{0,60}?\b(?:experience|exp\b|working|in\b|of\b))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Verdict:
    keep: bool
    family: str = ""        # key, e.g. "product_marketing"
    family_label: str = ""  # display, e.g. "Product Marketing"
    level: str = ""         # one of LEVELS
    reason: str = ""        # why it was dropped (or how the level was decided)


@lru_cache(maxsize=1)
def rules() -> dict:
    with open(ROLES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    flags = re.IGNORECASE
    lv = raw["levels"]
    return {
        "exclude": re.compile(raw["exclude"], flags),
        "adjacent": re.compile(raw["adjacent"], flags),
        "engineering": re.compile(raw.get("engineering") or r"(?!x)x", flags),
        "families": [(f["key"], f["label"], re.compile(f["pattern"], flags))
                     for f in raw["families"]],
        "levels": {k: re.compile(v, flags) for k, v in lv.items()},
        "entry_max_years": int(raw.get("experience", {}).get("entry_max_years", 2)),
    }


def family_labels() -> list[str]:
    seen, out = set(), []
    for _, label, _ in rules()["families"]:
        if label not in seen:
            seen.add(label)
            out.append(label)
    return out


def min_years(description: str | None) -> int | None:
    """Largest 'N years of experience' minimum the posting asks for, or None.

    The LARGEST minimum is the binding one ("2+ years in sales ... 5+ years
    closing enterprise deals" is a 5-year role). Capped at 15 so a company
    blurb ("for 25 years we have...") can't masquerade as a requirement.
    """
    if not description:
        return None
    found = [int(m.group(1)) for m in _YEARS_RE.finditer(description)]
    found = [n for n in found if n <= 15]
    return max(found) if found else None


def family_of(title: str) -> tuple[str, str] | None:
    r = rules()
    title = title.replace("_", " ")
    if r["exclude"].search(title) or r["adjacent"].search(title):
        return None
    for key, label, pattern in r["families"]:
        if pattern.search(title):
            if key != "gtm_engineering" and r["engineering"].search(title):
                return None
            return key, label
    return None


def classify(title: str, description: str | None = "",
             employment_type: str | None = "") -> Verdict:
    if not title:
        return Verdict(False, reason="no title")
    # "Sales Manager_Chinese Vertical": an underscore is a word character, so
    # it would hide "Manager" from every whole-word rule below.
    title = title.replace("_", " ")
    r = rules()
    lv = r["levels"]
    if r["exclude"].search(title):
        return Verdict(False, reason="excluded function")
    if r["adjacent"].search(title):
        return Verdict(False, reason="adjacent role")
    fam = None
    for key, label, pattern in r["families"]:
        if pattern.search(title):
            fam = (key, label)
            break
    if fam is None:
        return Verdict(False, reason="not a tracked role family")
    key, label = fam
    if key != "gtm_engineering" and r["engineering"].search(title):
        # "Software Engineer, Provider Growth" is a product engineering job.
        return Verdict(False, reason="engineering role")

    # Phrases where "lead"/"manage" is the job, not the seniority.
    bare = lv["senior_exempt"].sub(" ", title)
    hard = bool(lv["hard_senior"].search(bare))
    soft = bool(lv["soft_senior"].search(bare))

    is_intern = bool(lv["intern"].search(title)) or \
        (employment_type or "").strip().lower() in {"intern", "internship"}
    if is_intern:
        if hard or re.search(r"\bmanager\b", bare, re.IGNORECASE):
            return Verdict(False, key, label, reason="senior title mentioning interns")
        level = COOP if _COOP_RE.search(title) else INTERN
        return Verdict(True, key, label, level, "title/job type")

    if hard:
        return Verdict(False, key, label, reason="senior title")

    if lv["new_grad"].search(title):
        return Verdict(True, key, label, NEW_GRAD, "title")

    blocked = bool(lv["entry_blockers"].search(title))
    is_manager = bool(re.search(r"\bmanager\b", bare, re.IGNORECASE))
    years = min_years(description)
    max_entry = r["entry_max_years"]
    # "Associate Product Marketing Manager" is entry level; "Sales Development
    # Manager" runs the SDR team. Only an explicit junior word outranks "manager".
    titled_entry = not blocked and (
        bool(lv["entry_strong"].search(title))
        or (not is_manager and bool(lv["entry"].search(title)))
    )
    if titled_entry:
        # Some companies use "Associate" for mid-level roles. A posting that
        # asks for clearly more experience than entry level overrides the title.
        if years is not None and years >= max_entry + 2:
            return Verdict(False, key, label, reason=f"posting asks for {years}+ yr")
        return Verdict(True, key, label, ENTRY, "title")

    if is_manager:
        # A manager title with no junior word is not entry level, whatever a
        # stray "1 year" in the posting text says.
        return Verdict(False, key, label, reason="manager title")
    if years is not None:
        if years <= max_entry:
            return Verdict(True, key, label, ENTRY, f"posting asks for {years} yr")
        return Verdict(False, key, label, reason=f"posting asks for {years}+ yr")
    if soft:
        return Verdict(False, key, label, reason="segment title, no experience stated")
    return Verdict(True, key, label, UNCLEAR, "no level stated")
