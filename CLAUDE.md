# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick start

- **Run app**: `python app.py` — starts on port 5001
- **Demo login**: `demo@spendly.com` / `demo123`
- **Run tests**: `python -m pytest tests/test_<spec_name>.py -v`

## Architecture

Spendly is a Flask expense tracker built step-by-step as a learning project.

- **Routes**: all in `app.py`; session-based auth with werkzeug password hashing
- **Database**: SQLite (`spendly.db`); parameterized queries only — no ORM
- **Schema**: `users(id, name, email, password_hash, created_at)` and `expenses(id, user_id, amount, category, date, description, created_at)`
- **Templates**: Jinja2, all extend `base.html`; use `url_for()` for all links
- **CSS**: vanilla CSS with variables in `static/css/style.css` — never hardcode hex values
- **Categories**: exactly 7 fixed values — `Food, Transport, Bills, Health, Entertainment, Shopping, Other` — validate server-side

## Code conventions

- **SQL**: parameterized with `?` placeholders always; never string-format SQL
- **Passwords**: `generate_password_hash()` / `check_password_hash()` from werkzeug only
- **Dates**: store as `YYYY-MM-DD` strings; validate with `_DATE_RE`; reject future dates
- **Amounts**: floats > 0 only; reject zero or negative
- **Descriptions**: optional — store `None` as `NULL`; display as empty string in templates
- **Query helpers**: complex SQL lives in `database/queries.py`; `app.py` imports and calls them

## Important patterns

- **Auth guard**: `if not session.get("user_id"): return redirect(url_for("login"))`
- **Data isolation**: every query filters by `user_id` — never trust request data for ownership
- **Missing resources**: use `abort(404)` when a row isn't found or doesn't belong to the user
- **Form errors**: re-render the template with `error=` and `form=` to preserve field values
- **Date range filter**: use `_date_clause(date_from, date_to)` helper in `database/queries.py`
- **Foreign keys**: enabled via `PRAGMA foreign_keys = ON` in `get_db()`

## Testing

- Test files: `tests/test_<spec_name>.py`
- Read the matching `.claude/specs/` file to understand what to test — test intent, not implementation
- Run a single test: `pytest tests/test_07_add_expense.py::test_name -v`

## Workflow

- **Before implementing**: always read `.claude/specs/<step>-<name>.md` for requirements and definition of done
- **Commits**: Conventional Commits — `feat:`, `fix:`, `chore:` — describe what the *user* can now do
- **PRs**: plain English title; description includes spec overview, files changed, definition-of-done checklist
- **Slash commands**: `/create-spec`, `/test-feature`, `/code-review-feature`, `/ship-feature`, `/seed-user`, `/seed-expense`

## Gotchas

- Hooks file is `.claude/settings.json` — any edits to hooks go there
- Demo seed runs once on startup only (skips if `users` table is non-empty)
- The delete route at `/expenses/<id>/delete` is a stub — implemented in step 09
- Category breakdown percentages are normalized to sum to 100% (largest category absorbs rounding diff)
