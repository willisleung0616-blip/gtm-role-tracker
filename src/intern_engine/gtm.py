"""The go-to-market tracker's update run.

    fetch every board  ->  keep GTM roles at intern / new-grad / entry level
    ->  resolve US / Canada  ->  read posting text (experience, sponsorship)
    ->  store (first seen, open / closed)  ->  render the dashboard

This reuses the engine's fetch layer (connectors, rate limiting, circuit
breaker) and replaces the internship-cycle pipeline, which assumes every role
names a "Summer 2027"-style term. Entry-level and new-grad roles never do.

Companies carry a `tier` in data/companies.json:
  watchlist   hand-picked; always tracked, shown even with no open roles
  curated     from a named startup list; same treatment as watchlist
  discovered  everything else; listed only while the board looks like an
              active, growing employer (see `_board_is_active`)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections import Counter
from datetime import UTC, datetime, timedelta

from . import (
    enrich,
    filters,
    geo,
    h1b,
    health,
    models,
    names,
    paths,
    pipeline,
    quality,
    registry,
    roles,
    skills,
    sponsorship,
)

JOBS_PATH = os.path.join(paths.DATA_DIR, "gtm_jobs.json")
NEAR_PATH = os.path.join(paths.DATA_DIR, "gtm_not_listed.json")
BOARDS_PATH = os.path.join(paths.DATA_DIR, "gtm_boards.json")
STATS_PATH = os.path.join(paths.DATA_DIR, "gtm_stats.json")

WATCHLIST, CURATED, DISCOVERED = "watchlist", "curated", "discovered"

# Activity thresholds for `discovered` boards.
MIN_OPEN_ROLES = 10        # a board with fewer openings is not hiring at pace
MAX_OPEN_ROLES = 300       # larger than this is no longer a startup
RECENT_POST_DAYS = 30      # at least one posting this recent
GTM_MEMORY_DAYS = 90       # a GTM role seen this recently counts as "hires GTM"

CLOSE_AFTER_MISSES = 2     # consecutive complete reads without the role
PURGE_CLOSED_DAYS = 45
_DETAIL_CONCURRENCY = 8

# Boards that return the whole company; only these can be measured for size.
_WHOLE_BOARD = {"greenhouse", "lever", "ashby", "rippling", "breezy", "recruitee"}

_UNPAID_RE = re.compile(r"\bunpaid\b|\bcommission[- ]only\b|\bvolunteer\b", re.IGNORECASE)
_UNPAID_TEXT_RE = re.compile(
    r"\bunpaid (?:internship|position|role|opportunity)\b|\bthis (?:is an? )?unpaid\b|"
    r"\bcommission[- ]only\b|\b100% commission\b",
    re.IGNORECASE,
)
# "Summer 2027", "Winter/January 2027", and year-first "2027 Summer".
_TERM_RE = re.compile(
    r"\b(Summer|Fall|Autumn|Winter|Spring)\b[\s/,-]*(?:[A-Za-z]+[\s/,-]+)?(20\d\d)\b"
    r"|\b(20\d\d)\s+(Summer|Fall|Autumn|Winter|Spring)\b", re.IGNORECASE)

_CAREERS = {
    "greenhouse": "https://job-boards.greenhouse.io/{slug}",
    "ashby": "https://jobs.ashbyhq.com/{slug}",
    "lever": "https://jobs.lever.co/{slug}",
    "workable": "https://apply.workable.com/{slug}/",
    "rippling": "https://ats.rippling.com/{slug}/jobs",
    "breezy": "https://{slug}.breezy.hr",
    "recruitee": "https://{slug}.recruitee.com",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path: str, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def careers_url(company: dict) -> str:
    if company.get("careers_url"):
        return company["careers_url"]
    template = _CAREERS.get(company.get("ats"))
    if template:
        return template.format(slug=company["slug"])
    if company.get("ats") == "workday" and company.get("wd"):
        return (f"https://{company['slug']}.{company['wd']}.myworkdayjobs.com/"
                f"{company.get('site', '')}")
    return ""


def tier_of(company: dict) -> str:
    tier = company.get("tier")
    return tier if tier in (WATCHLIST, CURATED) else DISCOVERED


def stated_term(title: str, description: str | None = None) -> str:
    """The internship term the EMPLOYER stated ("Summer 2027"), or ""."""
    match = _TERM_RE.search(title or "")
    if match:
        word, year = (match.group(1), match.group(2)) if match.group(1) else (
            match.group(4), match.group(3))
        term = "Fall" if word.lower() == "autumn" else word.title()
        return f"{term} {year}"
    if re.search(r"\b20\d\d\b", title or ""):
        return ""  # the title names a year we could not pair with a term: do not guess
    if description:
        stated = filters.seasons_from_text(description)
        if stated:
            return stated[0]
    return ""


# --- classification of one fetched job --------------------------------------

def _needs_text(verdict: roles.Verdict, job) -> bool:
    """Would the posting text change the outcome, and do we lack it?"""
    if job.description is not None or job.source not in enrich._FETCHERS:
        return False
    if verdict.keep:
        return True  # kept roles need text for sponsorship and the experience check
    return verdict.reason.startswith("segment title")


def _apply(job, verdict: roles.Verdict, countries: list[str]) -> None:
    job.family = verdict.family_label
    job.level = verdict.level
    job.level_reason = verdict.reason
    job.countries = countries
    job.remote = bool(job.remote) or filters.is_remote(job.location, job.title)
    job.company = names.display(job.company, job.company_slug)
    if job.posted_at and not job.posted_at_source:
        job.posted_at_source = models.date_source(job.posted_at)


async def select(results, existing: dict, default_net, workday_net=None):
    """Turn raw fetch results into (kept jobs, per-board facts, seen ids).

    Detail pages are fetched only for roles that already pass the title and
    country checks, and only once per role: the store remembers the verdict.
    """
    blocklist = quality.load_blocklist()
    gate = asyncio.Semaphore(_DETAIL_CONCURRENCY)
    kept: list = []
    boards: dict[str, dict] = {}
    seen_by_board: dict[str, set[str]] = {}
    detail_requests = 0
    drops: Counter = Counter()
    near: list[dict] = []
    named: dict[str, dict] = {}

    def drop(job, reason: str, full: str | None = None) -> bool:
        """Count a drop; for named companies also keep the row, so "why isn't
        this role listed?" has an answer on the dashboard."""
        drops[reason] += 1
        board = named.get(job.board_key or "")
        if board and reason not in ("not a tracked role family", "excluded function"):
            near.append({"company": board["name"], "title": job.title,
                         "location": job.location, "reason": full or reason,
                         "url": job.url})
        return False

    async def text_for(job):
        nonlocal detail_requests
        fetcher = enrich._FETCHERS.get(job.source)
        if fetcher is None:
            return
        net = workday_net if (workday_net and job.source in ("workday", "oracle")) else default_net
        try:
            async with gate:
                job.description = await fetcher(job, net)
            detail_requests += 1
        except Exception:  # noqa: BLE001 - a dead detail page must not stop the run
            job.description = None

    async def one(job, company) -> bool:
        if job.description is not None:
            job.description = sponsorship.strip_html(job.description)
        first = roles.classify(job.title, job.description, job.employment_type)
        if not first.keep and not first.reason.startswith("segment title"):
            return drop(job, first.reason.split(" for ")[0], first.reason)
        # Cheap country check before paying for a detail page.
        countries, basis = geo.resolve(job.location, job.salary, job.description)
        if not countries and not geo.names_no_place(job.location):
            return drop(job, "outside US/Canada")

        prior = existing.get(job.id) or {}
        verdict = first
        if _needs_text(first, job):
            if prior.get("text_checked") and prior.get("title") == job.title:
                # Settled on an earlier run: reuse, no network.
                if not prior.get("level"):
                    why = prior.get("drop_reason") or "posting text"
                    return drop(job, why.split(" for ")[0], why)
                verdict = roles.Verdict(True, first.family, first.family_label,
                                        prior["level"], prior.get("level_reason", ""))
                job.sponsorship = prior.get("sponsorship", "unknown")
                job.salary = job.salary or prior.get("salary")
                if geo.names_no_place(job.location) and prior.get("location"):
                    job.location = prior["location"]  # detail page named the places
                if not countries:
                    countries = prior.get("countries") or []
            else:
                await text_for(job)
                if job.description is not None:
                    job.description = sponsorship.strip_html(job.description)
                verdict = roles.classify(job.title, job.description, job.employment_type)
                if not countries:
                    countries, basis = geo.resolve(job.location, job.salary, job.description)
        if not verdict.keep:
            drop(job, verdict.reason.split(" for ")[0], verdict.reason)
            if job.description is not None:
                # Remember the verdict so the detail page is not re-fetched.
                existing[job.id] = {**prior, "id": job.id, "title": job.title,
                                    "text_checked": True, "level": "",
                                    "drop_reason": verdict.reason, "open": False,
                                    "board_key": job.board_key,
                                    "last_seen": _stamp(_now())}
            return False

        text = job.description or ""
        if _UNPAID_RE.search(job.title) or _UNPAID_TEXT_RE.search(text):
            return drop(job, "unpaid or commission-only")
        if text:
            job.sponsorship = sponsorship.classify(text)
            job.salary = job.salary or skills.extract_pay(text)
        if not countries:
            countries, basis = geo.resolve(job.location, job.salary, text)
        if not countries:
            return drop(job, "no country stated")
        _apply(job, verdict, countries)
        job.category = stated_term(job.title, job.description) if verdict.level in (
            roles.INTERN, roles.COOP) else ""
        return True

    tasks = []
    for company, result, error in results:
        key = registry.board_key(company)
        jobs = result.jobs
        newest = max((j.posted_at or "" for j in jobs), default="")
        boards[key] = {
            "name": names.display(company["name"], company["slug"]),
            "tier": tier_of(company),
            "source_list": company.get("source_list", ""),
            "ats": company["ats"],
            "slug": company["slug"],
            "careers_url": careers_url(company),
            "ok": error is None,
            "error": (error or "")[:160],
            "complete": bool(result.complete),
            "whole_board": company["ats"] in _WHOLE_BOARD,
            "total_roles": len(jobs),
            "gtm_roles": sum(1 for j in jobs if roles.family_of(j.title)),
            "newest_posted": newest[:10],
        }
        seen_by_board[key] = {j.id for j in jobs}
        if boards[key]["tier"] in (WATCHLIST, CURATED):
            named[key] = boards[key]
        if error is not None or quality.is_blocked(company["name"], blocklist):
            continue
        for job in jobs:
            job.board_key = key
            tasks.append((job, company, key))

    verdicts = await asyncio.gather(*(one(job, company) for job, company, _ in tasks))
    for (job, _company, key), ok in zip(tasks, verdicts):
        if ok:
            kept.append(job)
    near.sort(key=lambda r: (r["company"].casefold(), r["title"].casefold()))
    return kept, boards, seen_by_board, {"detail_requests": detail_requests,
                                         "drops": dict(drops), "near_misses": near}


# --- board activity (the "fast-growing startup" test) ------------------------

def board_is_active(board: dict, memory: dict, now: datetime) -> tuple[bool, str]:
    """Does a `discovered` board look like an active, growing employer?"""
    if board["tier"] in (WATCHLIST, CURATED):
        return True, "tracked by name"
    if board["whole_board"]:
        if board["total_roles"] < MIN_OPEN_ROLES:
            return False, f"fewer than {MIN_OPEN_ROLES} open roles"
        if board["total_roles"] > MAX_OPEN_ROLES:
            return False, f"more than {MAX_OPEN_ROLES} open roles"
    newest = board.get("newest_posted")
    if newest:
        cutoff = (now - timedelta(days=RECENT_POST_DAYS)).strftime("%Y-%m-%d")
        if newest < cutoff:
            return False, f"no posting in {RECENT_POST_DAYS} days"
    last_gtm = memory.get("last_gtm_seen", "")
    cutoff = (now - timedelta(days=GTM_MEMORY_DAYS)).strftime("%Y-%m-%d")
    if not board["gtm_roles"] and last_gtm < cutoff:
        return False, "no go-to-market role seen recently"
    return True, "active"


# --- store ---------------------------------------------------------------------

def _record(job, board: dict, prior: dict, now: str, h1b_index: dict) -> dict:
    approvals = h1b.approvals_for(job.company, h1b_index) if geo.US in (job.countries or []) else None
    return {
        "id": job.id,
        "company": board["name"],
        "tier": board["tier"],
        "source_list": board.get("source_list", ""),
        "source": job.source,
        "board_key": job.board_key,
        "title": job.title,
        "family": job.family,
        "level": job.level,
        "level_reason": job.level_reason,
        "term": job.category if job.category != "Other" else "",
        "location": job.location,
        "countries": job.countries,
        "remote": bool(job.remote),
        "url": job.url,
        "department": job.department or "",
        "posted_at": job.posted_at or prior.get("posted_at") or "",
        "salary": job.salary or prior.get("salary") or "",
        "sponsorship": job.sponsorship if job.description is not None
        else prior.get("sponsorship", job.sponsorship),
        "h1b_approvals": approvals if approvals is not None else 0,
        "text_checked": bool(job.description is not None or prior.get("text_checked")),
        "first_seen": prior.get("first_seen") or now,
        "last_seen": now,
        "open": True,
        "misses": 0,
        "closed_at": "",
        "closed_reason": "",
    }


def _dedup(jobs: list) -> list:
    """One row per (company, title, location): a company with two boards
    (Wealthsimple runs Ashby and Lever) must not list a role twice."""
    seen: dict[tuple, object] = {}
    for job in sorted(jobs, key=lambda j: (j.posted_at or "9999", j.id)):
        key = (job.company.casefold(), job.title.casefold().strip(),
               (job.location or "").casefold().strip())
        seen.setdefault(key, job)
    return list(seen.values())


def update_store(existing: dict, kept: list, boards: dict, seen_by_board: dict,
                 active_boards: set[str], now: datetime) -> dict:
    stamp = _stamp(now)
    h1b_index = h1b.load()
    kept_ids = set()
    new_ids = []
    for job in _dedup(kept):
        if job.board_key not in active_boards:
            continue
        prior = existing.get(job.id) or {}
        if not prior.get("first_seen"):
            new_ids.append(job.id)
        existing[job.id] = _record(job, boards[job.board_key], prior, stamp, h1b_index)
        kept_ids.add(job.id)

    for jid, rec in existing.items():
        if jid in kept_ids or not rec.get("open"):
            continue
        key = rec.get("board_key")
        board = boards.get(key)
        if board is None:
            continue  # board not fetched this run (quarantined): leave as is
        if key not in active_boards:
            rec.update(open=False, closed_at=stamp, closed_reason="board no longer active")
        elif jid in seen_by_board.get(key, ()):
            # Still posted, but it no longer passes our own rules.
            rec.update(open=False, closed_at=stamp, closed_reason="out-of-scope")
        elif board["ok"] and board["complete"]:
            rec["misses"] = int(rec.get("misses") or 0) + 1
            if rec["misses"] >= CLOSE_AFTER_MISSES:
                rec.update(open=False, closed_at=stamp, closed_reason="gone-from-feed")

    cutoff = _stamp(now - timedelta(days=PURGE_CLOSED_DAYS))
    for jid in [j for j, r in existing.items()
                if not r.get("open") and (r.get("closed_at") or r.get("last_seen") or "") < cutoff]:
        del existing[jid]
    return {"new_ids": new_ids}


# --- the run -----------------------------------------------------------------

def run_update(limit_tiers: set[str] | None = None) -> dict:
    """Fetch, classify, store. Returns the stats written to gtm_stats.json."""
    started = _now()
    companies = registry.load()
    known = {registry.board_key(c) for c in companies}
    if limit_tiers:
        companies = [c for c in companies if tier_of(c) in limit_tiers]
    health_data = health.load()
    active, benched = health.partition(companies, health_data)
    existing = _load(JOBS_PATH, {})
    # Forget boards that were removed from data/companies.json.
    memory = {k: v for k, v in _load(BOARDS_PATH, {}).items() if k in known}

    async def after(results, default_net, workday_net):
        return await select(results, existing, default_net, workday_net)

    results, (kept, boards, seen_by_board, extra) = asyncio.run(
        pipeline._fetch_all(active, after))

    now = _now()
    today = now.strftime("%Y-%m-%d")
    for company, result, error in results:
        health.record(health_data, company, pipeline._fetch_health_error(result, error))
    health.save(health_data)

    active_boards: set[str] = set()
    inactive_reasons: Counter = Counter()
    for key, board in boards.items():
        mem = memory.get(key) or {}
        if board["gtm_roles"]:
            mem["last_gtm_seen"] = today
        ok, why = board_is_active(board, mem, now)
        board["active"] = ok
        board["active_reason"] = why
        board["last_gtm_seen"] = mem.get("last_gtm_seen", "")
        board["checked_at"] = _stamp(now)
        if ok:
            active_boards.add(key)
        else:
            inactive_reasons[why] += 1
        memory[key] = {**mem, **board}
    # Benched (quarantined) boards keep their last known facts.
    for company in benched:
        key = registry.board_key(company)
        memory.setdefault(key, {
            "name": company["name"], "tier": tier_of(company), "ats": company["ats"],
            "slug": company["slug"], "careers_url": careers_url(company),
            "ok": False, "error": "skipped: failing repeatedly", "total_roles": 0,
            "gtm_roles": 0, "active": tier_of(company) != DISCOVERED,
        })

    near_misses = extra.pop("near_misses", [])
    outcome = update_store(existing, kept, boards, seen_by_board, active_boards, now)
    listed = {k: len([r for r in existing.values() if r.get("open") and r.get("board_key") == k])
              for k in boards}
    for key, n in listed.items():
        memory[key]["listed_roles"] = n

    open_rows = [r for r in existing.values() if r.get("open")]
    stats = {
        "generated_at": _stamp(now),
        "duration_seconds": round((now - started).total_seconds(), 1),
        "boards_total": len(companies),
        "boards_fetched": sum(1 for b in boards.values() if b["ok"]),
        "boards_failed": sum(1 for b in boards.values() if not b["ok"]),
        "boards_skipped": len(benched),
        "boards_active": len(active_boards),
        "inactive_reasons": dict(inactive_reasons),
        "postings_read": sum(b["total_roles"] for b in boards.values()),
        "roles_open": len(open_rows),
        "roles_new": len(outcome["new_ids"]),
        "by_level": dict(Counter(r["level"] for r in open_rows)),
        "by_family": dict(Counter(r["family"] for r in open_rows)),
        "by_country": dict(Counter(c for r in open_rows for c in r["countries"])),
        "by_tier": dict(Counter(r["tier"] for r in open_rows)),
        **extra,
    }
    _save(JOBS_PATH, existing)
    _save(BOARDS_PATH, memory)
    _save(STATS_PATH, stats)
    _save(NEAR_PATH, near_misses)
    return stats


def load_all() -> tuple[dict, dict, dict]:
    return _load(JOBS_PATH, {}), _load(BOARDS_PATH, {}), _load(STATS_PATH, {})


def load_not_listed() -> list[dict]:
    return _load(NEAR_PATH, [])
