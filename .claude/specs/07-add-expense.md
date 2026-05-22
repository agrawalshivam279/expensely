# Spec: Add Expense Feature

## Overview
This feature implements the ability for logged-in users to add new expense entries via a form at `/expenses/add`. It replaces the current placeholder route with a fully functional GET/POST flow: the GET renders the form, and the POST validates input and inserts a row into the `expenses` table. On success the user is redirected to `/profile` where the new expense appears immediately in their transaction list.

## Depends on
- Step 01 — Database setup (expenses table exists)
- Step 03 — Login/logout (session-based auth)
- Step 05 — Backend routes for profile page (profile reflects live data)

## Routes
- `GET /expenses/add` — Render the add-expense form — logged-in only
- `POST /expenses/add` — Validate and insert the new expense, redirect to `/profile` — logged-in only

## Database changes
No new tables or columns. A new `INSERT` query helper will be added to `database/queries.py`.

## Templates
- **Create:** `templates/add_expense.html` — form with fields: amount, category (dropdown), date, description (optional)
- **Modify:** None

## Files to change
- `app.py` — replace placeholder `add_expense` route with GET/POST handler
- `database/queries.py` — add `add_expense(user_id, amount, category, date, description)` helper

## Files to create
- `templates/add_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (not applicable here, but password rules stand for other routes)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Redirect unauthenticated users to `/login`
- Amount must be a positive number (> 0); reject zero or negative values
- Category must be one of the seven fixed values: Food, Transport, Bills, Health, Entertainment, Shopping, Other — validate server-side
- Date must match `YYYY-MM-DD` format and must not be in the future
- Description is optional; store `None`/empty string as `NULL`
- On validation failure, re-render the form with an inline error message and preserve previously entered values
- On success, redirect to `/profile` with a flash message or query param confirming the expense was added

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in shows a form with amount, category dropdown, date, and description fields
- [ ] Submitting the form with valid data inserts a row into `expenses` and redirects to `/profile`
- [ ] The newly added expense appears in the profile transaction list immediately after redirect
- [ ] Submitting with a missing or zero/negative amount shows a validation error on the same form
- [ ] Submitting with an invalid category (e.g., tampered form value) shows a validation error
- [ ] Submitting with an incorrectly formatted or future date shows a validation error
- [ ] Previously entered values are preserved when the form is re-rendered after a validation error
