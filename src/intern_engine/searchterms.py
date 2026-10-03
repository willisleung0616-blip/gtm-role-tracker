"""Keywords sent to job boards that only offer keyword search.

Workday and Workable do not hand over a whole board; they answer a search.
The original engine searched "intern" / "co-op", which never returns an
"Account Executive" or a "Growth Marketing Associate". These terms cover the
go-to-market families in data/roles.json. Boards that return everything
(Greenhouse, Lever, Ashby, Rippling, ...) ignore this list.
"""

TERMS = ("marketing", "sales", "growth", "account executive",
         "business development", "go-to-market")
# Workable rate-limits anonymous bulk use hard; keep its sweep short.
TERMS_SHORT = ("marketing", "sales", "growth")
