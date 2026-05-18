# Spec: Login and Logout

## Overview
This step implements session-based authentication for Spendly. Users can log in with their email and password, and log out to end their session. Flask's built-in `session` object (backed by a signed cookie) is used to track the authenticated user across requests. This is the gateway feature that all protected routes will depend on — no expense data should be accessible without a valid session.

## Depends on
- Step 01 — Database Setup (users table must exist with hashed passwords)
- Step 02 — Registration (at least one real user must exist to log in with)

## Routes
- `GET /login` — render the login form — public
- `POST /login` — validate credentials, start session, redirect to dashboard — public
- `GET /logout` — clear session, redirect to landing page — logged-in (or graceful no-op if not logged in)

## Database changes
No database changes. The `users` table already has `email` and `password_hash` columns added in Step 01.

## Templates
- **Modify:** `templates/login.html` — add a POST form with email and password fields, an error message area, and a link to the registration page

## Files to change
- `app.py` — implement `POST /login` logic and `GET /logout` logic; set `app.secret_key`
- `templates/login.html` — add the login form with error display

## Files to create
No new files.

## New dependencies
No new dependencies. `werkzeug.security.check_password_hash` is already available via the existing Werkzeug install.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords verified with `werkzeug.security.check_password_hash` — never compare plaintext
- `app.secret_key` must be set before any session usage; use a hard-coded dev string for now (e.g. `"spendly-dev-secret"`)
- Store only `user_id` in the session — never store the full user row or password hash
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- After successful login redirect to `/` (landing or future dashboard); after logout redirect to `/`
- On failed login, re-render the login form with a generic error message ("Invalid email or password") — never reveal which field was wrong
- The `GET /logout` route must clear the session with `session.clear()` and redirect — no confirmation page needed

## Definition of done
- Visiting `/login` renders the login form without errors
- Submitting correct credentials (e.g. demo@spendly.com / demo123) redirects the user away from `/login`
- `session["user_id"]` is set after a successful login
- Submitting wrong email or wrong password shows the generic error message on the login page
- Visiting `/logout` clears the session and redirects to `/`
- After logout, `session.get("user_id")` returns `None`
- The login form is styled consistently with the rest of the app using CSS variables
- No plaintext passwords appear anywhere in the code or logs
