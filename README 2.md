# GTM Role Tracker

Tracks internships, co-ops, new-grad and entry-level roles in sales, GTM engineering, GTM and growth, growth marketing and product marketing, in the US and Canada. It reads each employer's own job board and builds one dashboard page.

Adapted from zshah101's internship engine (see `LICENSE` and `legacy_docs/`). The fetch layer is the original. The role rules, country check, pipeline and dashboard are new.

## Run it

Double-click **Run Tracker.command**. The first run sets itself up, reads about 2,500 job boards, and opens the dashboard. Later runs only re-read posting text for roles it hasn't seen before.

- **Run Tracker (watchlist only).command** is a fast run over your watchlist and the curated startups.
- The dashboard is `docs/index.html`. `docs/roles.csv` has the same rows.
- It needs Python 3.11 or newer.

From Terminal, the same things are `python3 run.py`, `python3 run.py quick` and `python3 run.py render`.

## Automatic updates

Double-click **Turn on automatic updates.command** once. From then on the tracker reads your watchlist and the curated startups every 15 minutes and every job board every 2 hours, in the background, while the Mac is awake. Refresh the dashboard page to see the latest. `auto_update.log` records each run. **Turn off automatic updates.command** stops it.

## Change what it tracks

| To change | Edit |
|---|---|
| Which titles count, and at what level | `data/roles.json` |
| Which companies are read, and their tier | `data/companies.json` |
| Companies to check by hand | `data/manual_companies.json` |
| Size and activity thresholds for startups | the constants at the top of `src/intern_engine/gtm.py` |

To add a company to your watchlist:

    python3 run.py add "Company Name" https://jobs.ashbyhq.com/their-board

After editing `data/roles.json`, run `python3 -m pytest tests/test_roles.py` to check the rules still behave.

## How a role gets listed

See `METHODOLOGY.md`.
