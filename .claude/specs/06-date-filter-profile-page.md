# Spec: Date Filter for Profile Page

## Overview
Step 6 adds a date-range filter to the profile page so users can narrow the
summary stats, transaction list, and category breakdown to a specific time
window. The filter is applied via URL query parameters (`from` and `to`) so
results are bookmarkable and shareable. Four preset shortcuts — This Month,
Last Month, Last 7 Days, and All Time — sit above the transactions section;
a custom date-range picker lets users enter any start and end date. All three
data sections (summary stats, recent transactions, category breakdown) update
together when the filter changes. No new tables are needed; the existing
`expenses.date` column (stored as `YYYY-MM-DD` text) is sufficient.

## Depends on
- Step 1: Database setup (`expenses` table with a `date` column)
- Step 2: Registration
- Step 3: Login / Logout (`session["user_id"]` set on login)
- Step 4: Profile page UI (template structure already in place)
- Step 5: Backend connection (live query helpers in `database/queries.py`)

## Routes
- `GET /profile` — same route, now accepts optional query params:
  - `from` — start date, format `YYYY-MM-DD` (inclusive)
  - `to` — end date, format `YYYY-MM-DD` (inclusive)
  - If either param is absent or invalid, the route falls back to All Time.

No new routes.

## Database changes
No database changes. The `expenses.date` column (`TEXT`, `YYYY-MM-DD`) is
already present and sufficient for range filtering.

## Templates
- **Modify:** `templates/profile.html`
  - Add a filter bar above the transactions section containing:
    - Four preset buttons: **This Month**, **Last Month**, **Last 7 Days**, **All Time**
    - A custom date range form with two `<input type="date">` fields and an **Apply** button
  - The active preset (or custom range) should be visually highlighted
  - All three data sections (stats, transactions, categories) already use
    Jinja variables — no structural changes needed, only the filter bar is new

## Files to change
- `app.py` — read `from` and `to` query params; validate and sanitise them;
  pass them into the four query helpers
- `database/queries.py` — add optional `date_from` and `date_to` keyword
  arguments to `get_summary_stats`, `get_recent_transactions`, and
  `get_category_breakdown`; add `WHERE … AND date BETWEEN ? AND ?` clauses
  when the arguments are provided
- `templates/profile.html` — add the filter bar UI described above

## Files to create
No new files.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format values into SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- Date param validation: accept only strings that match `YYYY-MM-DD`; reject
  anything else silently and fall back to no filter (All Time)
- `date_from` and `date_to` must default to `None`; queries must work
  correctly with or without them
- The filter bar form must use `GET` method so the date range appears in the URL
- Preset shortcuts must be implemented as anchor tags that append the
  appropriate `from` and `to` params to `/profile`; no JavaScript required for
  the presets (JS may be used only for the custom date picker UX if needed)
- The active filter state (which preset is highlighted) must be derived
  server-side from the current `from`/`to` params — not client-side JS state

## Definition of done
- [ ] Visiting `/profile` with no query params shows all expenses (All Time)
- [ ] Clicking **This Month** filters stats and transactions to the current calendar month
- [ ] Clicking **Last Month** filters stats and transactions to the previous calendar month
- [ ] Clicking **Last 7 Days** filters stats and transactions to the last 7 days (today inclusive)
- [ ] Entering a custom date range and clicking **Apply** filters all three sections to that range
- [ ] The active preset button is visually distinguished from the inactive ones
- [ ] With an active date filter, total spent and transaction count reflect only expenses in that range
- [ ] With an active date filter, the category breakdown reflects only expenses in that range
- [ ] An empty date range (no matching expenses) shows ₹0.00, 0 transactions, and an empty category list — no errors
- [ ] Invalid or missing `from`/`to` params fall back gracefully to All Time without a 500 error
