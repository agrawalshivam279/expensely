# Spec: Edit Expense

## Overview
This feature lets logged-in users edit any of their previously recorded expenses. Clicking an "Edit" button next to a transaction on the profile page navigates to a pre-filled form at `/expenses/<id>/edit`. The GET handler fetches the existing expense (verifying it belongs to the session user) and renders the form with all fields pre-populated. The POST handler validates the submitted values and updates the row in the `expenses` table, then redirects back to `/profile`. This completes the read–update side of the expense CRUD cycle started in Step 07.

## Depends on
- Step 01 — Database setup (expenses table exists)
- Step 03 — Login/logout (session-based auth)
- Step 04 & 05 — Profile page with transaction list (where the Edit button lives)
- Step 07 — Add expense (establishes the validation rules and form conventions)

## Routes
- `GET /expenses/<int:id>/edit` — Render edit form pre-filled with existing expense data — logged-in only
- `POST /expenses/<int:id>/edit` — Validate and update the expense, redirect to `/profile` — logged-in only

## Database changes
No new tables or columns. Two new query helpers will be added to `database/queries.py`.

## Templates
- **Create:** `templates/edit_expense.html` — pre-filled form with amount, category (dropdown), date, and description fields; shares the same validation error UX as `add_expense.html`
- **Modify:** `templates/profile.html` — add an "Actions" column to the transaction table with an Edit link per row (requires `id` field in each transaction dict)

## Files to change
- `app.py` — replace placeholder `edit_expense` route with GET/POST handler including auth check
- `database/queries.py` — add `get_expense_by_id(expense_id, user_id)` and `update_expense(expense_id, user_id, amount, category, date, description)` helpers; modify `get_recent_transactions` to include `id` in each returned dict
- `templates/profile.html` — add Actions column header and Edit link cell to the transactions table

## Files to create
- `templates/edit_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (not applicable here, convention stands)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Redirect unauthenticated users to `/login`
- `get_expense_by_id` must filter by both `id` AND `user_id` — if the row is not found (wrong owner or missing), return a 404 response (`abort(404)`)
- `update_expense` must also filter by both `id` AND `user_id` in the WHERE clause — never update a row the user does not own
- Amount must be a positive number (> 0); reject zero or negative values
- Category must be one of the seven fixed CATEGORIES values — validate server-side
- Date must match `YYYY-MM-DD` format and must not be in the future
- Description is optional; store `None`/empty string as `NULL`
- On validation failure, re-render `edit_expense.html` with an inline error message and preserve submitted values
- On success, redirect to `/profile`
- The edit form action must POST to the same `/expenses/<id>/edit` URL

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `/expenses/<id>/edit` for an expense that belongs to another user returns 404
- [ ] Visiting `/expenses/<id>/edit` while logged in shows a pre-filled form with the expense's existing values
- [ ] Submitting valid changes updates the expense in the database and redirects to `/profile`
- [ ] The updated values appear in the profile transaction list after the redirect
- [ ] Submitting with a missing or zero/negative amount shows a validation error on the edit form
- [ ] Submitting with an invalid category shows a validation error
- [ ] Submitting with an incorrectly formatted or future date shows a validation error
- [ ] Previously submitted values are preserved when the form re-renders after a validation error
- [ ] Each transaction row on the profile page has a visible "Edit" link that navigates to the correct edit URL
