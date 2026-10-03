"""Ashby job board API: public, no auth.

`includeCompensation=true` adds pay tiers, and each posting ships its full
description — so salary and sponsorship classification are free for Ashby.
"""

from __future__ import annotations

from ..models import Fetch, Job, clean_listing, source_board_key
from ..net import Net

URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"


def _salary(posting: dict) -> str | None:
    comp = posting.get("compensation")
    if isinstance(comp, dict):
        summary = comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary")
        if summary:
            return str(summary).strip()
    return None


def _place(name, address) -> str:
    """"Toronto" -> "Toronto, Ontario, Canada" using the board's own address.

    Ashby's location NAME is free text and usually a bare city, which says
    nothing about the country. The structured address beside it does.
    """
    name = (name or "").strip()
    postal = (address or {}).get("postalAddress") if isinstance(address, dict) else None
    extra: list[str] = []
    if isinstance(postal, dict):
        country = str(postal.get("addressCountry") or "").strip()
        region = str(postal.get("addressRegion") or "").strip()
        lowered = name.lower()
        # The name often already says it ("Toronto, ON, Canada"): add only what
        # is missing, and never a region once the country is already named.
        if country and country.lower() in lowered:
            pass
        else:
            if region and region.lower() not in lowered and region.lower() != country.lower():
                extra.append(region)
            if country:
                extra.append(country)
    return ", ".join([p for p in [name, *extra] if p])


def _location(posting: dict) -> str:
    places = [_place(posting.get("location"), posting.get("address"))]
    for other in posting.get("secondaryLocations") or []:
        if isinstance(other, dict):
            places.append(_place(other.get("location"), other.get("address")))
    seen, out = set(), []
    for place in places:
        if place and place.lower() not in seen:
            seen.add(place.lower())
            out.append(place)
    return "; ".join(out) or "—"


async def fetch(company: dict, net: Net) -> Fetch:
    slug = company["slug"]
    data = await net.get_json(URL.format(slug=slug))
    listing = clean_listing(data, "jobs")

    jobs = []
    for posting in (listing or []):
        if posting.get("isListed") is False:
            continue
        job_url = posting.get("jobUrl") or posting.get("applyUrl") or ""
        external = job_url.rstrip("/").rsplit("/", 1)[-1] if job_url else posting.get("title")
        jobs.append(
            Job(
                id=f"ashby:{slug}:{external}",
                source="ashby",
                company=company["name"],
                company_slug=slug,
                title=(posting.get("title") or "").strip(),
                location=_location(posting),
                url=job_url,
                posted_at=posting.get("publishedAt"),
                salary=_salary(posting),
                description=posting.get("descriptionPlain") or posting.get("descriptionHtml"),
                board_key=source_board_key(company, "ashby", slug),
                employment_type=posting.get("employmentType"),
                department=posting.get("department") or posting.get("team"),
                remote=bool(posting.get("isRemote")),
            )
        )
    return Fetch.board(jobs, isinstance(listing, list))
