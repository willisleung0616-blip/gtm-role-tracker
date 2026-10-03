# How the tracker decides

Every role is read from the employer's own job board (Ashby, Greenhouse, Lever, Rippling, Workable, Workday, Breezy, Recruitee). The link on each card is the employer's posting.

## 1. Role family

The title must match one family in `data/roles.json`: Product Marketing, Sales, GTM Engineering, Growth Marketing, GTM & Growth, or Marketing (other).

Dropped outright: recruiting, legal, finance, design and product management titles, even when they mention sales or growth ("GTM Recruiter", "Sales Finance"). Also dropped as adjacent: solutions and sales engineers, customer success, partnerships.

## 2. Level

| Level | What puts a role there |
|---|---|
| Internship, Co-op | The title says so, or the board's own job type is "Intern". |
| New grad | "New grad", "early career", "graduate program", "rotational program". |
| Entry level | Junior, associate, coordinator, assistant, SDR, BDR, "I" in the title; or the posting text asks for 2 years' experience or less. |
| Level unclear | Neither the title nor the posting says. Hidden by default on the dashboard. |

Dropped: senior, staff, principal, lead, head, director, VP, founding, "II" and above. A "manager" title is dropped unless it also says associate or junior. A title that reads as entry level is still dropped when its posting asks for 4 or more years.

When a posting gives several experience figures, the largest one counts.

## 3. Country

From the posting's location: country, state or province, or a known city. A role with several locations is kept if any is in the US or Canada.

When the location names no place ("Remote"), pay quoted in CAD counts as Canada and USD as the US. A bare "$" counts as nothing. A role with no country evidence is not listed.

## 4. Company

| Tier | Meaning |
|---|---|
| Watchlist | Named by you. Always read, always shown under Tracked companies. |
| Curated startup | From a named list (currently the Ben Lang startup list). Same treatment. |
| Other active companies | Any other board in `data/companies.json`, listed only while it has 10 to 300 open roles, a posting in the last 30 days, and a sales or marketing role seen in the last 90 days. |

Staffing agencies are blocked by name. Unpaid and commission-only roles are dropped.

Funding stage and valuation are not checked. There is no free source for them.

## 5. Visa tags

Read from the posting's own words, never inferred from the company.

- **Citizens or PR only**: requires US citizenship, a clearance, or Canadian citizenship or permanent residence.
- **No visa sponsorship**: says it will not sponsor, has no LMIA support, or requires an existing work permit.
- **Sponsorship offered**: says sponsorship is available.
- No tag: the posting says nothing conclusive. This is most postings.

**H-1B employer** means USCIS approved H-1B petitions for that employer. It describes the employer, not the role, and applies to US roles only.

## 6. Open and closed

A role closes when two complete reads of the board in a row no longer return it, or at once when it is still posted but no longer passes these rules. A partial read never closes anything. Closed roles are removed after 45 days.
