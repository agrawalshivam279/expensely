import sqlite3
import pytest
from werkzeug.security import generate_password_hash

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect every get_db() call to a fresh in-memory-like temp database."""
    db_path = str(tmp_path / "test.db")

    import database.db as db_module
    original_connect = sqlite3.connect

    def patched_get_db():
        conn = original_connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    monkeypatch.setattr(db_module, "get_db", patched_get_db)

    # Also patch the imported reference inside queries.py
    import database.queries as q_module
    monkeypatch.setattr(q_module, "get_db", patched_get_db)

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
def seed_user(isolated_db):
    conn = isolated_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123"), "2026-01-15 10:00:00"),
    )
    user_id = cursor.lastrowid
    expenses = [
        (user_id, 12.50,  "Food",          "2026-05-01", "Lunch at café"),
        (user_id, 35.00,  "Transport",     "2026-05-03", "Monthly bus pass"),
        (user_id, 120.00, "Bills",         "2026-05-05", "Electricity bill"),
        (user_id, 45.00,  "Health",        "2026-05-07", "Pharmacy"),
        (user_id, 20.00,  "Entertainment", "2026-05-10", "Movie tickets"),
        (user_id, 89.99,  "Shopping",      "2026-05-12", "New shoes"),
        (user_id, 15.00,  "Other",         "2026-05-14", "Miscellaneous"),
        (user_id, 8.75,   "Food",          "2026-05-16", "Coffee and snacks"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        expenses,
    )
    conn.commit()
    conn.close()
    return user_id


@pytest.fixture
def empty_user(isolated_db):
    conn = isolated_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("New User", "new@example.com", generate_password_hash("pass1234")),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


# ---------------------------------------------------------------------------
# get_user_by_id
# ---------------------------------------------------------------------------

class TestGetUserById:
    def test_returns_correct_fields(self, seed_user):
        result = get_user_by_id(seed_user)
        assert result is not None
        assert result["name"] == "Demo User"
        assert result["email"] == "demo@spendly.com"
        assert result["initials"] == "DU"
        assert result["member_since"] == "January 2026"

    def test_returns_none_for_missing_id(self, isolated_db):
        assert get_user_by_id(9999) is None


# ---------------------------------------------------------------------------
# get_summary_stats
# ---------------------------------------------------------------------------

class TestGetSummaryStats:
    def test_correct_stats_with_expenses(self, seed_user):
        result = get_summary_stats(seed_user)
        assert result["total_spent"] == "₹346.24"
        assert result["transaction_count"] == 8
        assert result["top_category"] == "Bills"

    def test_zero_stats_with_no_expenses(self, empty_user):
        result = get_summary_stats(empty_user)
        assert result["total_spent"] == "₹0.00"
        assert result["transaction_count"] == 0
        assert result["top_category"] == "—"


# ---------------------------------------------------------------------------
# get_recent_transactions
# ---------------------------------------------------------------------------

class TestGetRecentTransactions:
    def test_returns_list_with_correct_keys(self, seed_user):
        result = get_recent_transactions(seed_user)
        assert len(result) == 8
        for item in result:
            assert "date" in item
            assert "description" in item
            assert "category" in item
            assert "amount" in item

    def test_ordered_newest_first(self, seed_user):
        result = get_recent_transactions(seed_user)
        assert result[0]["date"] == "May 16"
        assert result[-1]["date"] == "May 1"

    def test_amount_formatted_with_rupee(self, seed_user):
        result = get_recent_transactions(seed_user)
        for item in result:
            assert item["amount"].startswith("₹")

    def test_empty_list_for_user_with_no_expenses(self, empty_user):
        assert get_recent_transactions(empty_user) == []

    def test_limit_respected(self, seed_user):
        result = get_recent_transactions(seed_user, limit=3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# get_category_breakdown
# ---------------------------------------------------------------------------

class TestGetCategoryBreakdown:
    def test_returns_all_categories(self, seed_user):
        result = get_category_breakdown(seed_user)
        names = [item["name"] for item in result]
        assert set(names) == {"Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"}

    def test_ordered_by_amount_descending(self, seed_user):
        result = get_category_breakdown(seed_user)
        assert result[0]["name"] == "Bills"

    def test_percentages_sum_to_100(self, seed_user):
        result = get_category_breakdown(seed_user)
        assert sum(item["percent"] for item in result) == 100

    def test_percent_values_are_integers(self, seed_user):
        result = get_category_breakdown(seed_user)
        for item in result:
            assert isinstance(item["percent"], int)

    def test_amount_formatted_with_rupee(self, seed_user):
        result = get_category_breakdown(seed_user)
        for item in result:
            assert item["amount"].startswith("₹")

    def test_empty_list_for_user_with_no_expenses(self, empty_user):
        assert get_category_breakdown(empty_user) == []


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

@pytest.fixture
def app_client(isolated_db, seed_user):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["SECRET_KEY"] = "test-secret"
    with flask_app.app.test_client() as client:
        yield client, seed_user


class TestProfileRoute:
    def test_unauthenticated_redirects_to_login(self, app_client):
        client, _ = app_client
        response = client.get("/profile")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]

    def test_authenticated_returns_200(self, app_client):
        client, user_id = app_client
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        response = client.get("/profile")
        assert response.status_code == 200

    def test_shows_real_user_name(self, app_client):
        client, user_id = app_client
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        response = client.get("/profile")
        assert b"Demo User" in response.data

    def test_shows_real_email(self, app_client):
        client, user_id = app_client
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        response = client.get("/profile")
        assert b"demo@spendly.com" in response.data

    def test_shows_rupee_symbol(self, app_client):
        client, user_id = app_client
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        response = client.get("/profile")
        assert "₹".encode() in response.data

    def test_total_spent_matches_seed_data(self, app_client):
        client, user_id = app_client
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        response = client.get("/profile")
        assert b"346.24" in response.data

    def test_top_category_is_bills(self, app_client):
        client, user_id = app_client
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
        response = client.get("/profile")
        assert b"Bills" in response.data
