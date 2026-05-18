# Spec: Registration

## Overview
This step implements user account creation for Spendly. A visitor fills in their name, email, and password; the app hashes the password, inserts a new row into the `users` table, and redirects them to the login page. This is the entry point for all real users — without it, only the seeded demo account can log in.

## Depends on
- Step 01 — Database Setup (`users` table must exist)

## Routes
- `GET /register` — render the registration form — public
- `POST /register` — validate input, create user, redirect to `/login` — public

## Database changes
No database changes. The `users` table already has all required columns (`name`, `email`, `password_hash`) from Step 01.

## Templates
- **Modify:** `templates/register.html` — already has the POST form with `name`, `email`, `password` fields and `{% if error %}` block; no changes needed

## Files to change
- `app.py` — add `POST /register` handler; add `generate_password_hash` to imports; add `request` and `redirect` to Flask imports

## Files to create
No new files.

## New dependencies
No new dependencies. `werkzeug.security.generate_password_hash` is already available.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash` — never store plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- On duplicate email, catch the `sqlite3.IntegrityError` and re-render the form with the error `"An account with that email already exists"`
- On success, redirect to `/login` — do not auto-login the user after registration
- Minimum password length of 8 characters must be enforced server-side (not just via HTML `minlength`)
- Never expose which field caused a DB error beyond the email-taken message

## Definition of done
- Visiting `GET /register` renders the form without errors
- Submitting the form with a new name, email, and password (≥ 8 chars) inserts a row into `users` and redirects to `/login`
- The stored `password_hash` is a werkzeug hash — not plaintext
- Submitting with an already-registered email shows `"An account with that email already exists"` on the form
- Submitting with a password shorter than 8 characters shows a validation error on the form
- After registration, the new user can log in with their credentials at `/login`
