"""
tests/test_07_add_expense.py

Pytest tests for Step 07: Add Expense Feature (Spendly).

Spec: .claude/specs/07-add-expense.md

Coverage:
- Auth guard: GET and POST to /expenses/add while logged out redirect to /login
- GET form render: form contains amount, category dropdown (all 7 values), date, description fields
- Happy path POST: valid data inserts a row into expenses and redirects to /profile
- DB side effect: the new expense row exists in the DB with correct field values
- DB side effect: optional description is stored as NULL when omitted
- Validation: missing, zero, or negative amount re-renders form with error
- Validation: non-numeric amount re-renders form with error
- Validation: category not in the 7 fixed values re-renders form with error
- Validation: bad date format re-renders form with error (multiple formats tested)
- Validation: future date re-renders form with error
- Value preservation: previously entered values survive re-render after each validation failure
- Edge case: very large amount accepted
- Edge case: description with SQL-injection-like input is stored safely
"""

import sqlite3
import sys
import os
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# Path bootstrap — ensures imports work from both repo root and tests/
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Fixed categories as defined in the spec
VALID_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]

# A date guaranteed to be in the past regardless of when the suite runs
PAST_DATE = "2024-01-15"

# A date guaranteed to be in the future
FUTURE_DATE = (date.today() + timedelta(days=10)).isoformat()

# Today's date, which is the boundary for the "not in the future" rule
TODAY = date.today().isoformat()


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Redirect every get_db() call to a fresh temp-file database per test.
    Patches both database.db.get_db and the reference imported into
    database.queries so both modules see the same isolated connection factory.
    This prevents any test from touching the real spendly.db on disk.
    """
    db_path = str(tmp_path / "test_spendly.db")

    import database.db as db_module

    original_connect = sqlite3.connect

    def patched_get_db():
        conn = original_connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(db_module, "get_db", patched_get_db)

    import database.queries as q_module
    monkeypatch.setattr(q_module, "get_db", patched_get_db)

    # Bootstrap schema without seeding demo data
    conn = patched_get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        );
    """)
    conn.close()

    yield patched_get_db


@pytest.fixture
def test_user(isolated_db):
    """
    Insert a single user with no expenses and return their user_id.
    Tests that need a clean slate for DB side-effect verification use this.
    """
    conn = isolated_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Test User", "testuser@spendly.com", generate_password_hash("securepass123")),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


@pytest.fixture
def flask_client(isolated_db, test_user):
    """
    A Flask test client backed by the isolated DB.
    Returns (client, user_id). Session is NOT pre-authenticated.
    """
    import app as flask_app_module
    flask_app_module.app.config["TESTING"] = True
    flask_app_module.app.config["SECRET_KEY"] = "test-secret"
    with flask_app_module.app.test_client() as client:
        yield client, test_user


@pytest.fixture
def auth_client(flask_client):
    """
    Flask test client with session["user_id"] already set to the test user.
    Returns (client, user_id).
    """
    client, user_id = flask_client
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client, user_id


# ===========================================================================
# Helper — query the isolated DB directly for DB side-effect assertions
# ===========================================================================

def _fetch_all_expenses(isolated_db_factory, user_id):
    """Return all expense rows for the given user as a list of sqlite3.Row objects."""
    conn = isolated_db_factory()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


# ===========================================================================
# 1. Auth Guard
# ===========================================================================

class TestAuthGuard:
    """Unauthenticated requests to /expenses/add must be redirected to /login."""

    def test_unauthenticated_get_redirects_to_login(self, flask_client):
        client, _ = flask_client
        response = client.get("/expenses/add")
        assert response.status_code == 302, (
            "GET /expenses/add while logged out must return 302"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect target must be /login"
        )

    def test_unauthenticated_post_redirects_to_login(self, flask_client):
        client, _ = flask_client
        response = client.post("/expenses/add", data={
            "amount": "25.00",
            "category": "Food",
            "date": PAST_DATE,
            "description": "Lunch",
        })
        assert response.status_code == 302, (
            "POST /expenses/add while logged out must return 302"
        )
        assert "/login" in response.headers["Location"], (
            "Redirect target must be /login"
        )

    def test_unauthenticated_post_does_not_insert_expense(self, flask_client, isolated_db, test_user):
        client, user_id = flask_client
        client.post("/expenses/add", data={
            "amount": "25.00",
            "category": "Food",
            "date": PAST_DATE,
            "description": "Lunch",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 0, (
            "Unauthenticated POST must not insert any expense into the database"
        )


# ===========================================================================
# 2. GET — Form Render
# ===========================================================================

class TestGetFormRender:
    """Authenticated GET /expenses/add must render the add-expense form."""

    def test_authenticated_get_returns_200(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        assert response.status_code == 200, (
            "Authenticated GET /expenses/add must return HTTP 200"
        )

    def test_form_contains_amount_field(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        html = response.data.decode("utf-8", errors="replace").lower()
        assert 'name="amount"' in html, (
            "Form must contain an input with name='amount'"
        )

    def test_form_contains_category_field(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        html = response.data.decode("utf-8", errors="replace").lower()
        assert 'name="category"' in html, (
            "Form must contain a field with name='category'"
        )

    def test_form_contains_date_field(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        html = response.data.decode("utf-8", errors="replace").lower()
        assert 'name="date"' in html, (
            "Form must contain an input with name='date'"
        )

    def test_form_contains_description_field(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        html = response.data.decode("utf-8", errors="replace").lower()
        assert 'name="description"' in html, (
            "Form must contain an input or textarea with name='description'"
        )

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_category_dropdown_contains_all_seven_values(self, auth_client, category):
        client, _ = auth_client
        response = client.get("/expenses/add")
        assert category.encode() in response.data, (
            f"Category dropdown must contain the option '{category}'"
        )

    def test_form_uses_post_method(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        html = response.data.decode("utf-8", errors="replace").lower()
        assert 'method="post"' in html or "method='post'" in html, (
            "Add expense form must submit via POST"
        )

    def test_form_action_points_to_add_expense_route(self, auth_client):
        client, _ = auth_client
        response = client.get("/expenses/add")
        html = response.data.decode("utf-8", errors="replace")
        assert "/expenses/add" in html, (
            "Form action must point to /expenses/add"
        )


# ===========================================================================
# 3. Happy Path POST
# ===========================================================================

class TestHappyPathPost:
    """Valid form submissions must insert a row and redirect to /profile."""

    def test_valid_post_redirects_to_profile(self, auth_client):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "42.50",
            "category": "Food",
            "date": PAST_DATE,
            "description": "Dinner out",
        })
        assert response.status_code == 302, (
            "Valid POST must redirect (302)"
        )
        assert "/profile" in response.headers["Location"], (
            "Successful POST must redirect to /profile"
        )

    def test_valid_post_with_description_inserts_row(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "42.50",
            "category": "Food",
            "date": PAST_DATE,
            "description": "Dinner out",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 1, "Exactly one expense row must be inserted after a valid POST"

    def test_valid_post_stores_correct_amount(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "42.50",
            "category": "Food",
            "date": PAST_DATE,
            "description": "Dinner out",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert abs(rows[0]["amount"] - 42.50) < 0.001, (
            "Stored amount must match the submitted value"
        )

    def test_valid_post_stores_correct_category(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "99.00",
            "category": "Transport",
            "date": PAST_DATE,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert rows[0]["category"] == "Transport", (
            "Stored category must match the submitted value"
        )

    def test_valid_post_stores_correct_date(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "15.00",
            "category": "Bills",
            "date": PAST_DATE,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert rows[0]["date"] == PAST_DATE, (
            "Stored date must match the submitted value"
        )

    def test_valid_post_stores_correct_description(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "8.00",
            "category": "Other",
            "date": PAST_DATE,
            "description": "Coffee beans",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert rows[0]["description"] == "Coffee beans", (
            "Stored description must match the submitted value"
        )

    def test_valid_post_stores_description_as_null_when_omitted(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "20.00",
            "category": "Health",
            "date": PAST_DATE,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert rows[0]["description"] is None, (
            "Empty description must be stored as NULL in the database"
        )

    def test_valid_post_stores_correct_user_id(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "55.00",
            "category": "Shopping",
            "date": PAST_DATE,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert rows[0]["user_id"] == user_id, (
            "Stored user_id must match the logged-in user's ID"
        )

    def test_valid_post_today_date_is_accepted(self, auth_client, isolated_db, test_user):
        """The boundary date (today) must be accepted — spec says 'must not be in the future'."""
        client, user_id = auth_client
        response = client.post("/expenses/add", data={
            "amount": "10.00",
            "category": "Entertainment",
            "date": TODAY,
            "description": "",
        })
        assert response.status_code == 302, (
            "Today's date must be accepted as valid (boundary condition)"
        )
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 1, "Expense with today's date must be inserted into the DB"

    @pytest.mark.parametrize("category", VALID_CATEGORIES)
    def test_each_valid_category_is_accepted(self, auth_client, isolated_db, test_user, category):
        """Every one of the 7 fixed categories must be accepted on a valid POST."""
        client, user_id = auth_client
        response = client.post("/expenses/add", data={
            "amount": "5.00",
            "category": category,
            "date": PAST_DATE,
            "description": "",
        })
        assert response.status_code == 302, (
            f"Category '{category}' must be accepted and produce a redirect"
        )
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 1, f"One expense must be inserted for category '{category}'"

    def test_expense_appears_in_profile_after_redirect(self, auth_client):
        """After a successful POST, following the redirect to /profile must return 200."""
        client, _ = auth_client
        response = client.post(
            "/expenses/add",
            data={
                "amount": "77.00",
                "category": "Shopping",
                "date": PAST_DATE,
                "description": "New jacket",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200, (
            "Following the redirect to /profile after a successful POST must return 200"
        )


# ===========================================================================
# 4. Validation: Amount
# ===========================================================================

class TestValidationAmount:
    """Missing, zero, or negative amount must re-render the form with an error."""

    def test_missing_amount_returns_200_not_redirect(self, auth_client):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "",
            "category": "Food",
            "date": PAST_DATE,
            "description": "",
        })
        assert response.status_code == 200, (
            "Missing amount must re-render the form (200), not redirect"
        )

    def test_missing_amount_shows_error_message(self, auth_client):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "",
            "category": "Food",
            "date": PAST_DATE,
            "description": "",
        })
        html = response.data.decode("utf-8", errors="replace").lower()
        assert "error" in html or "amount" in html, (
            "Form re-render after missing amount must contain an error message"
        )

    def test_missing_amount_does_not_insert_expense(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "",
            "category": "Food",
            "date": PAST_DATE,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 0, "No expense must be inserted when amount is missing"

    def test_zero_amount_returns_200_not_redirect(self, auth_client):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "0",
            "category": "Food",
            "date": PAST_DATE,
            "description": "",
        })
        assert response.status_code == 200, (
            "Zero amount must re-render the form (200), not redirect"
        )

    def test_zero_amount_shows_error_message(self, auth_client):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "0",
            "category": "Food",
            "date": PAST_DATE,
            "description": "",
        })
        assert b"zero" in response.data.lower() or b"error" in response.data.lower() or b"greater" in response.data.lower(), (
            "Error message must indicate the amount must be greater than zero"
        )

    def test_zero_amount_does_not_insert_expense(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "0",
            "category": "Food",
            "date": PAST_DATE,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 0, "No expense must be inserted when amount is zero"

    @pytest.mark.parametrize("bad_amount", ["-1", "-0.01", "-100", "-999.99"])
    def test_negative_amount_returns_200_not_redirect(self, auth_client, bad_amount):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": bad_amount,
            "category": "Food",
            "date": PAST_DATE,
            "description": "",
        })
        assert response.status_code == 200, (
            f"Negative amount '{bad_amount}' must re-render the form, not redirect"
        )

    @pytest.mark.parametrize("bad_amount", ["-1", "-0.01", "-100", "-999.99"])
    def test_negative_amount_does_not_insert_expense(self, auth_client, isolated_db, test_user, bad_amount):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": bad_amount,
            "category": "Food",
            "date": PAST_DATE,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 0, (
            f"No expense must be inserted for negative amount '{bad_amount}'"
        )

    @pytest.mark.parametrize("bad_amount", ["abc", "12.34.56", "one hundred", "$50", " "])
    def test_non_numeric_amount_returns_200_not_redirect(self, auth_client, bad_amount):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": bad_amount,
            "category": "Food",
            "date": PAST_DATE,
            "description": "",
        })
        assert response.status_code == 200, (
            f"Non-numeric amount '{bad_amount}' must re-render the form, not redirect"
        )

    @pytest.mark.parametrize("bad_amount", ["abc", "12.34.56", "one hundred", "$50", " "])
    def test_non_numeric_amount_does_not_insert_expense(self, auth_client, isolated_db, test_user, bad_amount):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": bad_amount,
            "category": "Food",
            "date": PAST_DATE,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 0, (
            f"No expense must be inserted for non-numeric amount '{bad_amount}'"
        )

    def test_very_large_valid_amount_is_accepted(self, auth_client, isolated_db, test_user):
        """A very large positive number must be accepted — spec only rejects <= 0."""
        client, user_id = auth_client
        response = client.post("/expenses/add", data={
            "amount": "9999999.99",
            "category": "Other",
            "date": PAST_DATE,
            "description": "",
        })
        assert response.status_code == 302, (
            "A very large positive amount must be accepted and produce a redirect"
        )
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 1, "Very large valid amount must be inserted into the database"


# ===========================================================================
# 5. Validation: Category
# ===========================================================================

class TestValidationCategory:
    """A category value outside the 7 fixed options must be rejected server-side."""

    @pytest.mark.parametrize("bad_category", [
        "Groceries",
        "Rent",
        "Travel",
        "food",           # wrong case
        "FOOD",           # all caps
        "",               # empty string
        "Food; DROP TABLE expenses; --",  # SQL injection attempt
        "invalid_cat",
    ])
    def test_invalid_category_returns_200_not_redirect(self, auth_client, bad_category):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "25.00",
            "category": bad_category,
            "date": PAST_DATE,
            "description": "",
        })
        assert response.status_code == 200, (
            f"Invalid category '{bad_category}' must re-render the form (200), not redirect"
        )

    @pytest.mark.parametrize("bad_category", [
        "Groceries",
        "Rent",
        "food",
        "",
        "Food; DROP TABLE expenses; --",
    ])
    def test_invalid_category_does_not_insert_expense(self, auth_client, isolated_db, test_user, bad_category):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "25.00",
            "category": bad_category,
            "date": PAST_DATE,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 0, (
            f"No expense must be inserted for invalid category '{bad_category}'"
        )

    def test_invalid_category_shows_error_message(self, auth_client):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "25.00",
            "category": "Groceries",
            "date": PAST_DATE,
            "description": "",
        })
        html = response.data.decode("utf-8", errors="replace").lower()
        assert "error" in html or "invalid" in html or "category" in html, (
            "Form must display an error message for an invalid category"
        )


# ===========================================================================
# 6. Validation: Date Format
# ===========================================================================

class TestValidationDateFormat:
    """Dates not in YYYY-MM-DD format must be rejected with a form re-render."""

    @pytest.mark.parametrize("bad_date", [
        "15-01-2024",        # DD-MM-YYYY
        "01/15/2024",        # MM/DD/YYYY
        "2024/01/15",        # YYYY/MM/DD
        "Jan 15, 2024",      # Human-readable
        "2024-1-15",         # Missing leading zero on month
        "2024-01-5",         # Missing leading zero on day
        "not-a-date",        # Completely invalid
        "",                  # Empty string
        "2024-13-01",        # Invalid month 13
        "2024-00-15",        # Invalid month 00
        "2024-01-32",        # Invalid day 32
    ])
    def test_bad_date_format_returns_200_not_redirect(self, auth_client, bad_date):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "30.00",
            "category": "Food",
            "date": bad_date,
            "description": "",
        })
        assert response.status_code == 200, (
            f"Bad date '{bad_date}' must re-render the form (200), not redirect"
        )

    @pytest.mark.parametrize("bad_date", [
        "15-01-2024",
        "01/15/2024",
        "not-a-date",
        "",
    ])
    def test_bad_date_format_does_not_insert_expense(self, auth_client, isolated_db, test_user, bad_date):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "30.00",
            "category": "Food",
            "date": bad_date,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 0, (
            f"No expense must be inserted for bad date format '{bad_date}'"
        )

    def test_bad_date_format_shows_error_message(self, auth_client):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "30.00",
            "category": "Food",
            "date": "01/15/2024",
            "description": "",
        })
        html = response.data.decode("utf-8", errors="replace").lower()
        assert "error" in html or "date" in html or "format" in html, (
            "Form must display an error message for an incorrectly formatted date"
        )


# ===========================================================================
# 7. Validation: Future Date
# ===========================================================================

class TestValidationFutureDate:
    """A date in the future must be rejected — spec says date must not be in the future."""

    def test_future_date_returns_200_not_redirect(self, auth_client):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Health",
            "date": FUTURE_DATE,
            "description": "",
        })
        assert response.status_code == 200, (
            "Future date must re-render the form (200), not redirect"
        )

    def test_future_date_shows_error_message(self, auth_client):
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Health",
            "date": FUTURE_DATE,
            "description": "",
        })
        html = response.data.decode("utf-8", errors="replace").lower()
        assert "error" in html or "future" in html or "date" in html, (
            "Form must display an error message when the date is in the future"
        )

    def test_future_date_does_not_insert_expense(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Health",
            "date": FUTURE_DATE,
            "description": "",
        })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 0, "No expense must be inserted when the date is in the future"

    def test_far_future_date_rejected(self, auth_client, isolated_db, test_user):
        client, user_id = auth_client
        far_future = (date.today() + timedelta(days=3650)).isoformat()  # 10 years from now
        response = client.post("/expenses/add", data={
            "amount": "10.00",
            "category": "Other",
            "date": far_future,
            "description": "",
        })
        assert response.status_code == 200, (
            "A date far in the future must also be rejected and re-render the form"
        )
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 0, "No expense must be inserted for a date far in the future"


# ===========================================================================
# 8. Value Preservation on Validation Error
# ===========================================================================

class TestValuePreservation:
    """
    Spec: 'On validation failure, re-render the form with an inline error message
    and preserve previously entered values.'
    The previously entered values must appear in the re-rendered HTML so the user
    does not have to re-type everything from scratch.
    """

    def test_previously_entered_amount_preserved_on_error(self, auth_client):
        """When category is invalid, the submitted amount must still appear in the form."""
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "123.45",
            "category": "InvalidCat",
            "date": PAST_DATE,
            "description": "",
        })
        assert b"123.45" in response.data, (
            "Previously entered amount must be preserved in the re-rendered form"
        )

    def test_previously_entered_category_preserved_on_error(self, auth_client):
        """When the date is bad, the submitted category must still be pre-selected."""
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "50.00",
            "category": "Transport",
            "date": "not-a-date",
            "description": "",
        })
        assert b"Transport" in response.data, (
            "Previously entered category must be preserved in the re-rendered form"
        )

    def test_previously_entered_date_preserved_on_error(self, auth_client):
        """When the amount is invalid, the submitted date must still appear in the form."""
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "0",
            "category": "Bills",
            "date": PAST_DATE,
            "description": "",
        })
        assert PAST_DATE.encode() in response.data, (
            "Previously entered date must be preserved in the re-rendered form"
        )

    def test_previously_entered_description_preserved_on_error(self, auth_client):
        """When the amount is negative, the submitted description must still appear."""
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "-5.00",
            "category": "Entertainment",
            "date": PAST_DATE,
            "description": "Cinema ticket",
        })
        assert b"Cinema ticket" in response.data, (
            "Previously entered description must be preserved in the re-rendered form"
        )

    def test_all_values_preserved_on_future_date_error(self, auth_client):
        """All four fields must survive re-render when date is in the future."""
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "88.00",
            "category": "Shopping",
            "date": FUTURE_DATE,
            "description": "New headphones",
        })
        assert b"88.00" in response.data, "Amount must be preserved on future date error"
        assert b"Shopping" in response.data, "Category must be preserved on future date error"
        assert FUTURE_DATE.encode() in response.data, "Date must be preserved on future date error"
        assert b"New headphones" in response.data, "Description must be preserved on future date error"

    def test_all_values_preserved_on_invalid_category_error(self, auth_client):
        """All four fields must survive re-render when category is tampered."""
        client, _ = auth_client
        response = client.post("/expenses/add", data={
            "amount": "25.99",
            "category": "TamperedCategory",
            "date": PAST_DATE,
            "description": "Groceries",
        })
        assert b"25.99" in response.data, "Amount must be preserved on invalid category error"
        assert PAST_DATE.encode() in response.data, "Date must be preserved on invalid category error"
        assert b"Groceries" in response.data, "Description must be preserved on invalid category error"


# ===========================================================================
# 9. Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Additional edge cases from the spec's correctness contract."""

    def test_description_with_sql_injection_stored_safely(self, auth_client, isolated_db, test_user):
        """
        A description containing SQL-injection syntax must be stored as plain text,
        not interpreted. Parameterised queries prevent injection; this test verifies
        the application does not crash and the literal string is stored.
        """
        client, user_id = auth_client
        injection_payload = "'; DROP TABLE expenses; --"
        response = client.post("/expenses/add", data={
            "amount": "10.00",
            "category": "Other",
            "date": PAST_DATE,
            "description": injection_payload,
        })
        assert response.status_code == 302, (
            "SQL-injection-like description must not crash the application"
        )
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 1, "Expense must be inserted even when description contains SQL syntax"
        assert rows[0]["description"] == injection_payload, (
            "SQL-injection string must be stored literally, not interpreted"
        )

    def test_multiple_sequential_expenses_inserted_correctly(self, auth_client, isolated_db, test_user):
        """Multiple valid POSTs must each insert a separate row for the same user."""
        client, user_id = auth_client
        for i in range(3):
            client.post("/expenses/add", data={
                "amount": str(10.00 * (i + 1)),
                "category": "Food",
                "date": PAST_DATE,
                "description": f"Expense {i}",
            })
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 3, "Three sequential valid POSTs must produce three expense rows"

    def test_expenses_of_different_users_are_isolated(self, isolated_db, flask_client):
        """
        An expense added by user A must not appear when querying user B's expenses.
        This verifies the user_id is correctly stored and filtered.
        """
        client, user_a_id = flask_client  # already has test_user

        # Create a second user directly in the DB
        conn = isolated_db()
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("User B", "userb@spendly.com", generate_password_hash("bpassword")),
        )
        user_b_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Log in as user A and add an expense
        with client.session_transaction() as sess:
            sess["user_id"] = user_a_id
        client.post("/expenses/add", data={
            "amount": "99.00",
            "category": "Health",
            "date": PAST_DATE,
            "description": "User A expense",
        })

        # User B should have zero expenses
        rows_b = _fetch_all_expenses(isolated_db, user_b_id)
        assert len(rows_b) == 0, (
            "Expenses added by user A must not appear under user B's expense rows"
        )

        # User A should have exactly one expense
        rows_a = _fetch_all_expenses(isolated_db, user_a_id)
        assert len(rows_a) == 1, "User A must have exactly one expense"

    def test_whitespace_only_description_stored_as_null(self, auth_client, isolated_db, test_user):
        """
        Spec: 'Description is optional; store None/empty string as NULL.'
        A description of only whitespace characters must be treated as empty and stored as NULL.
        """
        client, user_id = auth_client
        response = client.post("/expenses/add", data={
            "amount": "5.00",
            "category": "Other",
            "date": PAST_DATE,
            "description": "   ",  # whitespace only
        })
        assert response.status_code == 302, (
            "Whitespace-only description must not cause a validation error"
        )
        rows = _fetch_all_expenses(isolated_db, user_id)
        assert len(rows) == 1, "Expense must be inserted"
        assert rows[0]["description"] is None, (
            "Whitespace-only description must be stored as NULL"
        )
