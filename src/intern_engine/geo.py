"""Which country is a role in: US, Canada, both, or neither?

Evidence, strongest first:
  1. the posting's own location text (country, state/province, known city);
  2. only when that says nothing about a country ("Remote", blank, a region
     name): the pay currency. CAD means the employer is hiring in Canada, USD
     in the US. A bare "$" proves nothing and is ignored.

A role that still has no country is NOT listed. We do not guess.
"""

from __future__ import annotations

import re

from . import filters

US = "US"
CANADA = "Canada"

_SPLIT_RE = re.compile(r"\s*(?:;|\||/|\bor\b|\band\b|\n)\s*", re.IGNORECASE)

_CA_CITIES = (
    "toronto", "vancouver", "montreal", "montréal", "ottawa", "calgary", "edmonton",
    "waterloo", "kitchener", "winnipeg", "halifax", "victoria", "quebec city",
    "mississauga", "burnaby", "markham", "kelowna", "saskatoon", "regina",
    "hamilton", "gta",
)
_US_CITIES = (
    "new york", "nyc", "san francisco", "sf", "bay area", "los angeles", "seattle",
    "austin", "boston", "chicago", "denver", "atlanta", "miami", "dallas",
    "houston", "san diego", "san jose", "palo alto", "mountain view", "menlo park",
    "sunnyvale", "santa clara", "redwood city", "washington dc", "washington, dc",
    "washington d.c.", "washington, d.c.", "philadelphia", "phoenix", "tempe",
    "salt lake city", "portland", "nashville", "charlotte", "raleigh", "pittsburgh",
    "minneapolis", "detroit", "brooklyn", "santa monica", "boulder", "lehi",
    "san mateo", "oakland", "cambridge, ma", "bellevue", "las vegas", "tampa",
    "orlando", "columbus", "indianapolis", "st. louis", "kansas city",
)


def _city_re(names) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(re.escape(n) for n in names) + r")(?![\w-])",
                      re.IGNORECASE)


_CA_CITY_RE = _city_re(_CA_CITIES)
_US_CITY_RE = _city_re(_US_CITIES)
_NORTH_AMERICA_RE = re.compile(r"\bnorth america\b|\bus\s*(?:&|and|/)\s*canada\b|\bcanada\s*(?:&|and|/)\s*us\b",
                               re.IGNORECASE)
# Words that carry no country at all.
_NO_PLACE_RE = re.compile(
    r"\b(?:remote|hybrid|anywhere|global|worldwide|distributed|virtual|home|office|"
    r"work from|wfh|flexible|multiple locations?|\d+\s+locations?|various|tbd|n/?a|americas?|amer)\b|[—\-–,()]",
    re.IGNORECASE,
)

# Office codes some boards use as the whole location: "US-SF-HQ", "US-NYC".
_US_PREFIX_RE = re.compile(r"^US[-–][A-Z]")

_CAD_RE = re.compile(r"\bCAD\b|\bC\$|\bCA\$|\bCDN\b|canadian dollars?", re.IGNORECASE)
_USD_RE = re.compile(r"\bUSD\b|\bUS\$|u\.?s\.? dollars?", re.IGNORECASE)


def currency(*texts: str | None) -> str | None:
    """"CAD", "USD", or None when neither or BOTH appear."""
    blob = " ".join(t for t in texts if t)
    cad, usd = bool(_CAD_RE.search(blob)), bool(_USD_RE.search(blob))
    if cad and not usd:
        return "CAD"
    if usd and not cad:
        return "USD"
    return None


def _from_location(location: str) -> set[str]:
    found: set[str] = set()
    if _NORTH_AMERICA_RE.search(location):
        return {US, CANADA}
    for part in [location, *_SPLIT_RE.split(location)]:
        part = part.strip()
        if not part:
            continue
        if filters.is_united_states(part) or _US_PREFIX_RE.match(part):
            found.add(US)
        elif filters.is_canada(part):
            found.add(CANADA)
        elif _CA_CITY_RE.search(part):
            found.add(CANADA)
        elif _US_CITY_RE.search(part):
            found.add(US)
    return found


def names_no_place(location: str | None) -> bool:
    """True for "Remote", "—", "" — text that names no place at all."""
    text = (location or "").strip()
    return not _NO_PLACE_RE.sub(" ", text).strip()


def resolve(location: str | None, salary: str | None = None,
            description: str | None = None) -> tuple[list[str], str]:
    """(countries, basis). countries is [] when the role is out of scope."""
    text = (location or "").strip()
    found = _from_location(text) if text else set()
    if found:
        return sorted(found, reverse=True), "location"   # "US" before "Canada"
    if names_no_place(text):
        code = currency(salary) or currency(description)
        if code == "CAD":
            return [CANADA], "pay currency"
        if code == "USD":
            return [US], "pay currency"
    return [], "none"
