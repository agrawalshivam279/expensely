# Spec: Delete Expense

## Overview
Allow logged-in users to permanently delete one of their own expenses. A delete button appears next to the Edit button in the Transaction History on the profile page. Because HTML forms only support GET and POST, deletion is handled via a POST request (not a GET) to prevent accidental or cross-site deletion. After deletion the user is redirected back to the profile page.

## Depends on
- Step 07 — Add Expense (expenses table and add flow)
- Step 08 — Edit Expense (edit button already present in profile.html; delete sits alongside it)

## Routes
- `POST /expenses/<id>/delete` — delete the expense with the given id if it belongs to the logged-in user, then redirect to `/profile` — logged-in only

> The existing stub at this path is a GET. Replace it with a POST-only handler.

## Database changes
No database changes. The `expenses` table already exists. A new query helper `delete_expense(expense_id, user_id)` will be added to `database/queries.py`.

## Templates
- **Modify:** `templates/profile.html`
  - Add a delete `<form>` (method POST, action `url_for('delete_expense', id=t.id)`) with a submit button styled as a danger button, placed next to the existing Edit link in the Transaction History loop.

## Files to change
- `app.py` — replace the stub `delete_expense` route with a real POST handler
- `database/queries.py` — add `delete_expense(expense_id, user_id)` helper
- `templates/profile.html` — add delete button/form next to Edit in the transaction list

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only (`?` placeholders)
- Passwords hashed with werkzeug (not relevant here, but maintain the pattern)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Route must be POST — a GET to this URL must not delete anything
- Always filter by both `id` AND `user_id` in the DELETE query — never trust the id alone
- Use `abort(404)` if the expense is not found or doesn't belong to the logged-in user
- Auth guard: redirect to login if `user_id` not in session

## Definition of done
- [ ] Visiting `GET /expenses/<id>/delete` does **not** delete the expense (405 or redirect)
- [ ] A "Delete" button is visible next to the Edit button on the profile page for each expense
- [ ] Clicking Delete submits a POST form and removes the expense from the database
- [ ] After deletion the user is redirected to `/profile` and the deleted expense no longer appears
- [ ] A logged-out user POSTing to `/expenses/<id>/delete` is redirected to login, not served the page
- [ ] A user cannot delete another user's expense — attempting to do so returns 404
- [ ] Deleting a non-existent expense id returns 404
