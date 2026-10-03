"""Renders docs/index.html (one self-contained page) and docs/roles.csv.

The page template is gtm_page.html, next to this file. The run's data is
embedded into it, so the page works opened from disk or served as a static
site. All filtering happens in the browser. The only outside request is the
web fonts; without a connection the page falls back to system fonts.
"""

from __future__ import annotations

import csv
import json
import os

from . import paths

ROLES_CSV_PATH = os.path.join(paths.DOCS_DIR, "roles.csv")
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gtm_page.html")

_ROW_FIELDS = (
    "id", "company", "tier", "source_list", "title", "family", "level", "level_reason",
    "term", "location", "countries", "remote", "url", "posted_at", "first_seen",
    "salary", "sponsorship", "h1b_approvals",
)
_CSV_FIELDS = (
    "company", "title", "family", "level", "term", "location", "countries", "remote",
    "salary", "sponsorship", "h1b_approvals", "posted_at", "first_seen", "tier", "url",
)


def _rows(store: dict) -> list[dict]:
    rows = [{k: r.get(k, "") for k in _ROW_FIELDS}
            for r in store.values() if r.get("open") and r.get("level")]
    rows.sort(key=lambda r: (r["posted_at"] or r["first_seen"] or ""), reverse=True)
    return rows


def _companies(boards: dict) -> list[dict]:
    """Named (watchlist / curated) companies, one row each even with two boards."""
    merged: dict[str, dict] = {}
    for board in boards.values():
        if board.get("tier") not in ("watchlist", "curated"):
            continue
        name = board.get("name") or board.get("slug")
        row = merged.setdefault(name.casefold(), {
            "name": name, "tier": board["tier"], "source_list": board.get("source_list", ""),
            "careers_url": board.get("careers_url", ""), "listed": 0, "total": 0,
            "gtm": 0, "ok": False, "error": "",
        })
        row["listed"] += int(board.get("listed_roles") or 0)
        row["total"] += int(board.get("total_roles") or 0)
        row["gtm"] += int(board.get("gtm_roles") or 0)
        row["ok"] = row["ok"] or bool(board.get("ok"))
        if not board.get("ok") and not row["error"]:
            row["error"] = board.get("error", "")
        if board.get("tier") == "watchlist":
            row["tier"] = "watchlist"
    return sorted(merged.values(), key=lambda r: (r["tier"] != "watchlist", r["name"].casefold()))


def write_csv(rows: list[dict]) -> None:
    os.makedirs(paths.DOCS_DIR, exist_ok=True)
    with open(ROLES_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_CSV_FIELDS)
        for r in rows:
            writer.writerow([
                " / ".join(r[k]) if isinstance(r[k], list) else r[k] for k in _CSV_FIELDS
            ])


def generate(store: dict, boards: dict, stats: dict, manual: list[dict] | None = None,
             not_listed: list[dict] | None = None) -> int:
    rows = _rows(store)
    payload = {
        "rows": rows,
        "companies": _companies(boards),
        "manual": manual or [],
        "not_listed": not_listed or [],
        "stats": stats,
    }
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    os.makedirs(paths.DOCS_DIR, exist_ok=True)
    with open(paths.DASHBOARD_PATH, "w", encoding="utf-8") as f:
        with open(TEMPLATE_PATH, encoding="utf-8") as template:
            f.write(template.read().replace("/*__DATA__*/null", blob))
    write_csv(rows)
    return len(rows)
