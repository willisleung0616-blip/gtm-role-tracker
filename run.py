"""GTM Role Tracker: command-line entry point.

    python3 run.py            read every job board, then rebuild the dashboard
    python3 run.py quick      only your watchlist and the curated startups (fast)
    python3 run.py render     rebuild the dashboard from the last run (no network)
    python3 run.py add "Company Name" <job board link>
                              start tracking a company by name, e.g.
                              python3 run.py add "Venn" https://jobs.ashbyhq.com/venn

The dashboard is written to docs/index.html. Open it in any browser.
(The original internship engine's commands live on in legacy_run.py.)
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

if sys.version_info < (3, 11):
    sys.exit("This tracker needs Python 3.11 or newer. You have "
             f"{sys.version_info.major}.{sys.version_info.minor}. "
             "Install a newer one from https://www.python.org/downloads/")

from intern_engine import gtm, gtm_dashboard, paths, registry  # noqa: E402

MANUAL_PATH = os.path.join(paths.DATA_DIR, "manual_companies.json")

_BOARD_URLS = (
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)", re.I)),
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([^/?#&]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([^/?#]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([^/?#]+)", re.I)),
    ("rippling", re.compile(r"ats\.rippling\.com/([^/?#]+)", re.I)),
    ("breezy", re.compile(r"//([^./]+)\.breezy\.hr", re.I)),
    ("recruitee", re.compile(r"//([^./]+)\.recruitee\.com", re.I)),
)


def _manual() -> list[dict]:
    if not os.path.exists(MANUAL_PATH):
        return []
    with open(MANUAL_PATH, encoding="utf-8") as f:
        return json.load(f)


def render() -> int:
    store, boards, stats = gtm.load_all()
    return gtm_dashboard.generate(store, boards, stats, _manual(), gtm.load_not_listed())


def summary(stats: dict, listed: int) -> None:
    print()
    print(f"Read {stats['boards_fetched']} of {stats['boards_total']} job boards "
          f"({stats['postings_read']:,} postings) in {stats['duration_seconds']:.0f}s.")
    if stats.get("boards_failed"):
        print(f"  {stats['boards_failed']} boards could not be read this time.")
    print(f"Listed {listed} matching roles ({stats['roles_new']} new).")
    for label, key in (("By level", "by_level"), ("By role", "by_family"),
                       ("By country", "by_country")):
        parts = ", ".join(f"{k} {v}" for k, v in sorted(
            stats.get(key, {}).items(), key=lambda kv: -kv[1]))
        print(f"  {label}: {parts or 'none'}")
    print(f"\nDashboard: {paths.DASHBOARD_PATH}")


def add(name: str, url: str) -> None:
    for ats, pattern in _BOARD_URLS:
        match = pattern.search(url)
        if match:
            slug = match.group(1)
            break
    else:
        sys.exit("That link isn't a job board this tracker can read. It needs to be "
                 "an Ashby, Greenhouse, Lever, Workable, Rippling, Breezy or Recruitee link.")
    companies = registry.load()
    for c in companies:
        if c["ats"] == ats and c["slug"].lower() == slug.lower():
            c["tier"] = "watchlist"
            c["name"] = name
            registry.save(companies)
            print(f"{name} was already in the list; it is now on your watchlist.")
            return
    companies.append({"name": name, "slug": slug, "ats": ats, "tier": "watchlist"})
    registry.save(companies)
    print(f"Added {name} ({ats}: {slug}) to your watchlist. Run the tracker to fetch its roles.")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    if cmd in ("update", "quick"):
        tiers = {gtm.WATCHLIST, gtm.CURATED} if cmd == "quick" else None
        print("Reading job boards. A full run takes a few minutes..." if tiers is None
              else "Reading your watchlist and curated startups...")
        stats = gtm.run_update(tiers)
        summary(stats, render())
    elif cmd == "render":
        print(f"Rebuilt the dashboard with {render()} roles: {paths.DASHBOARD_PATH}")
    elif cmd == "add" and len(sys.argv) == 4:
        add(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
