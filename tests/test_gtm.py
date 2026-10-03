"""End-to-end checks of the GTM run, offline: fake boards in, store out."""
import asyncio
from datetime import UTC, datetime, timedelta

from intern_engine import geo, gtm, models, roles


def job(slug, n, title, location, description="", source="ashby", **extra):
    return models.Job(
        id=f"{source}:{slug}:{n}", source=source, company=slug.title(), company_slug=slug,
        title=title, location=location, url=f"https://example.com/{slug}/{n}",
        posted_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        description=description, **extra,
    )


def board(slug, jobs, tier=None, ats="ashby", complete=True):
    company = {"name": slug.title(), "slug": slug, "ats": ats}
    if tier:
        company["tier"] = tier
    return company, models.Fetch(jobs, complete=complete), None


def run(results, existing=None):
    existing = {} if existing is None else existing
    kept, boards, seen, extra = asyncio.run(gtm.select(results, existing, None))
    now = datetime.now(UTC)
    active = set()
    for key, b in boards.items():
        mem = {"last_gtm_seen": now.strftime("%Y-%m-%d")} if b["gtm_roles"] else {}
        ok, _ = gtm.board_is_active(b, mem, now)
        b["active"] = ok
        if ok:
            active.add(key)
    gtm.update_store(existing, kept, boards, seen, active, now)
    return existing, boards, extra


def titles(store):
    return sorted(r["title"] for r in store.values() if r.get("open"))


def test_watchlist_board_keeps_only_early_career_gtm_roles_in_scope():
    store, _, extra = run([board("venn", [
        job("venn", 1, "Business Development Representative", "Toronto, Ontario, Canada"),
        job("venn", 2, "Account Executive, SMB", "Toronto, Ontario, Canada",
            "You bring 1+ years of experience in a closing role."),
        job("venn", 3, "Senior Account Executive", "Toronto, Ontario, Canada"),
        job("venn", 4, "Account Executive", "London, United Kingdom", "1 year of experience"),
        job("venn", 5, "Account Executive", "Toronto", "You have 5+ years of experience."),
        job("venn", 6, "Senior Frontend Engineer", "Toronto"),
        job("venn", 7, "Growth Marketing Intern (Summer 2027)", "Remote", "Pay: $25/hr CAD"),
        job("venn", 8, "Marketing Coordinator", "Remote", "Great team."),
    ], tier="watchlist")])
    assert titles(store) == [
        "Account Executive, SMB",
        "Business Development Representative",
        "Growth Marketing Intern (Summer 2027)",
    ]
    by_title = {r["title"]: r for r in store.values() if r.get("open")}
    intern = by_title["Growth Marketing Intern (Summer 2027)"]
    assert intern["level"] == roles.INTERN and intern["term"] == "Summer 2027"
    assert intern["countries"] == [geo.CANADA] and intern["remote"] is True
    assert by_title["Account Executive, SMB"]["level"] == roles.ENTRY
    assert extra["drops"]["no country stated"] == 1      # the "Remote" coordinator
    assert extra["drops"]["outside US/Canada"] == 1


def test_discovered_board_needs_to_look_like_an_active_employer():
    sdr = lambda slug, n: job(slug, n, "Sales Development Representative", "Austin, TX")  # noqa: E731
    filler = lambda slug, k: [job(slug, 100 + i, "Software Engineer", "Austin, TX") for i in range(k)]  # noqa: E731
    store, boards, _ = run([
        board("tiny", [sdr("tiny", 1)] + filler("tiny", 3)),
        board("growing", [sdr("growing", 1)] + filler("growing", 12)),
        board("named", [sdr("named", 1)], tier="curated"),
    ])
    companies = sorted(r["company"] for r in store.values() if r.get("open"))
    assert companies == ["Growing", "Named"]
    assert boards["ashby:tiny"]["active"] is False


def test_role_closes_after_two_complete_misses_and_at_once_when_out_of_scope():
    first = [board("acme", [
        job("acme", 1, "Sales Development Representative", "New York, NY"),
        job("acme", 2, "Marketing Coordinator", "New York, NY"),
    ], tier="watchlist")]
    store, _, _ = run(first)
    assert len(titles(store)) == 2

    # Role 1 vanishes; role 2 is retitled into a senior role (still posted).
    second = [board("acme", [job("acme", 2, "Senior Marketing Manager", "New York, NY")],
                    tier="watchlist")]
    store, _, _ = run(second, store)
    assert store["ashby:acme:2"]["open"] is False
    assert store["ashby:acme:2"]["closed_reason"] == "out-of-scope"
    assert store["ashby:acme:1"]["open"] is True          # one miss only arms it
    store, _, _ = run(second, store)
    assert store["ashby:acme:1"]["open"] is False
    assert store["ashby:acme:1"]["closed_reason"] == "gone-from-feed"


def test_partial_snapshot_never_closes_a_role():
    store, _, _ = run([board("acme", [job("acme", 1, "SDR", "Boston, MA")], tier="watchlist")])
    empty = [board("acme", [], tier="watchlist", complete=False)]
    for _ in range(3):
        store, _, _ = run(empty, store)
    assert store["ashby:acme:1"]["open"] is True


def test_same_role_on_two_boards_is_listed_once():
    a = board("wealth", [job("wealth", 1, "Growth Associate", "Toronto, ON")], tier="watchlist")
    b_company = {"name": "Wealth", "slug": "wealth", "ats": "lever", "tier": "watchlist"}
    b = (b_company, models.Fetch([job("wealth", 9, "Growth Associate", "Toronto, ON", source="lever")]), None)
    store, _, _ = run([a, b])
    assert len(titles(store)) == 1


def test_named_company_drops_are_recorded_with_a_reason():
    results = [board("venn", [
        job("venn", 1, "Senior Account Executive", "Toronto, Ontario, Canada"),
        job("venn", 2, "Account Executive", "London, United Kingdom"),
        job("venn", 3, "Backend Engineer", "Toronto"),
    ], tier="watchlist")]
    _, _, extra = run(results)
    near = {r["title"]: r["reason"] for r in extra["near_misses"]}
    assert near == {"Senior Account Executive": "senior title",
                    "Account Executive": "outside US/Canada"}


def test_workday_style_location_count_names_no_place():
    assert geo.names_no_place("2 Locations")
    assert geo.resolve("2 Locations")[0] == []
    assert geo.resolve("2 Locations", "$70,000 CAD")[0] == [geo.CANADA]


def test_office_code_locations():
    assert geo.resolve("US-SF-HQ")[0] == [geo.US]
    assert geo.resolve("LOCATION")[0] == []


def test_pay_currency_only_breaks_ties():
    assert geo.resolve("Remote", "$90k CAD")[0] == [geo.CANADA]
    assert geo.resolve("Remote", "$90k USD")[0] == [geo.US]
    assert geo.resolve("Remote", "$90k")[0] == []
    assert geo.resolve("London, UK", "$90k USD")[0] == []          # a named place wins
    assert geo.resolve("Toronto", "$90k USD")[0] == [geo.CANADA]


def test_old_closed_roles_are_purged():
    old = (datetime.now(UTC) - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    store = {"x": {"id": "x", "open": False, "closed_at": old, "board_key": "ashby:gone"}}
    store, _, _ = run([board("acme", [], tier="watchlist")], store)
    assert "x" not in store


def test_stated_term_reads_the_title_forms_employers_use():
    assert gtm.stated_term("Sales Intern (Summer 2027)") == "Summer 2027"
    assert gtm.stated_term("2027 Summer Sales Internship") == "Summer 2027"
    assert gtm.stated_term("Product Marketing Intern (Winter/January 2027, 12 Months)") == "Winter 2027"
    assert gtm.stated_term("2027 BT RISE Internship", "Join us for Fall 2027.") == ""
    assert gtm.stated_term("Marketing Intern") == ""
