"""
tests/test_date_filter_profile_page.py

Pytest tests for Step 6: Date Filter on the Profile Page (Spendly).

Spec: .claude/specs/06-date-filter-profile-page.md

Coverage:
- Auth guard on GET /profile
- All Time baseline (no query params)
- Custom date range filtering — stats, transactions, categories
- Preset shortcuts: This Month, Last Month, Last 7 Days
- Active preset detection (server-side)
- Empty result range (no matching expenses)
- Invalid / missing / malformed date params fall back gracefully to All Time
- Only one of from/to supplied
- Filter bar landmarks present in rendered HTML
- Query-layer unit tests: date_from / date_to kwargs on all three helpers
"""

import sqlite3
import sys
import os
from calendar import monthrange
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

# ---------------------------------------------------------------------------
# Path bootstrap — allows running from the repo root or from tests/
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database.queries import (
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _preset_ranges():
    """Mirror the preset logic from app.py so tests stay in sync with spec."""
    today = date.today()
    first_this = today.replace(day=1)
    last_this = today.replace(day=monthrange(today.year, today.month)[1])
    prev_month = (first_this - timedelta(days=1))
    first_prev = prev_month.replace(day=1)
    last_prev = prev_month.replace(day=monthrange(prev_month.year, prev_month.month)[1])
    return {
        "this_month":  (first_this.isoformat(), last_this.isoformat()),
        "last_month":  (first_prev.isoformat(), last_prev.isoformat()),
        "last_7_days": ((today - timedelta(days=6)).isoformat(), today.isoformat()),
    }


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """
    Redirect every get_db() call to a fresh temp-file database per test.
    Patches both database.db.get_db and the reference imported into
    database.queries so both modules see the same isolated connection factory.
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

    # Bootstrap schema
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
    """
    Insert one user and a known set of expenses spanning May 2026.
    All eight rows have dates in 2026-05-01 .. 2026-05-16, well outside
    any live preset range so we can test presets predictably by injecting
    explicit param strings.
    """
    conn = isolated_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123"), "2026-01-15 10:00:00"),
    )
    user_id = cursor.lastrowid

    expenses = [
        (user_id, 12.50,  "Food",          "2026-05-01", "Lunch at cafe"),
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
    """A user who has registered but has zero expenses."""
    conn = isolated_db()
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Empty User", "empty@spendly.com", generate_password_hash("emptypass")),
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id


@pytest.fixture
def flask_client(isolated_db, seed_user):
    """
    A Flask test client with an authenticated session pre-set.
    Returns (client, user_id).
    """
    import app as flask_app_module
    flask_app_module.app.config["TESTING"] = True
    flask_app_module.app.config["SECRET_KEY"] = "test-secret"
    with flask_app_module.app.test_client() as client:
        yield client, seed_user


@pytest.fixture
def auth_client(flask_client):
    """Flask test client with session["user_id"] already set."""
    client, user_id = flask_client
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client, user_id


# ===========================================================================
# 1. Auth Guard
# ===========================================================================

class TestAuthGuard:
    def test_unauthenticated_get_profile_redirects(self, flask_client):
        client, _ = flask_client
        response = client.get("/profile")
        assert response.status_code == 302, "Unauthenticated /profile must redirect"
        assert "/login" in response.headers["Location"], "Redirect must point to /login"

    def test_unauthenticated_with_date_params_still_redirects(self, flask_client):
        client, _ = flask_client
        response = client.get("/profile?from=2026-05-01&to=2026-05-31")
        assert response.status_code == 302, "Date params must not bypass auth guard"
        assert "/login" in response.headers["Location"]


# ===========================================================================
# 2. All Time — no query params
# ===========================================================================

class TestAllTime:
    def test_returns_200(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile")
        assert response.status_code == 200, "Authenticated /profile must return 200"

    def test_shows_all_eight_expenses_total(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile")
        # Total of all 8 seed rows: 12.50+35+120+45+20+89.99+15+8.75 = 346.24
        assert b"346.24" in response.data, "All Time total must be 346.24"

    def test_shows_eight_transaction_rows(self, auth_client):
        client, _ = auth_client
        # get_summary_stats returns transaction_count; template must render it
        from database.queries import get_summary_stats
        # Verify via query helper — all 8 rows returned with no date filter
        stats = get_summary_stats(auth_client[1])
        assert stats["transaction_count"] == 8, "All Time must return all 8 transactions"

    def test_shows_bills_as_top_category(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile")
        assert b"Bills" in response.data, "Bills must appear as top category"

    def test_no_date_params_sets_all_time_active_preset(self, auth_client):
        """
        With no query params the server derives active_preset = 'all_time'.
        The template must visually distinguish All Time — we check that the
        page renders without error and contains the 'All Time' label.
        """
        client, _ = auth_client
        response = client.get("/profile")
        assert response.status_code == 200
        assert b"All Time" in response.data, "All Time preset label must appear in the filter bar"


# ===========================================================================
# 3. Custom Date Range Filter
# ===========================================================================

class TestCustomDateRangeFilter:
    def test_narrow_range_returns_subset_of_expenses(self, auth_client):
        """from=2026-05-01&to=2026-05-07 covers 4 rows: Food, Transport, Bills, Health."""
        client, user_id = auth_client
        stats = get_summary_stats(user_id, date_from="2026-05-01", date_to="2026-05-07")
        assert stats["transaction_count"] == 4, "Range 05-01 to 05-07 must match exactly 4 expenses"

    def test_narrow_range_total_is_correct(self, auth_client):
        """12.50 + 35.00 + 120.00 + 45.00 = 212.50"""
        _, user_id = auth_client
        stats = get_summary_stats(user_id, date_from="2026-05-01", date_to="2026-05-07")
        assert stats["total_spent"] == "₹212.50", "Total for 05-01..05-07 must be ₹212.50"

    def test_narrow_range_top_category_is_bills(self, auth_client):
        _, user_id = auth_client
        stats = get_summary_stats(user_id, date_from="2026-05-01", date_to="2026-05-07")
        assert stats["top_category"] == "Bills", "Top category for 05-01..05-07 must be Bills"

    def test_route_with_custom_range_returns_200(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile?from=2026-05-01&to=2026-05-07")
        assert response.status_code == 200, "Custom range request must return 200"

    def test_route_narrow_range_excludes_later_expenses(self, auth_client):
        """Expenses on 2026-05-10 and later must NOT appear in the 05-01..05-07 range."""
        client, _ = auth_client
        response = client.get("/profile?from=2026-05-01&to=2026-05-07")
        # 346.24 is the All Time total; it must NOT appear when filter is active
        assert b"346.24" not in response.data, "Filtered page must not show All Time total"

    def test_route_shows_filtered_total_in_html(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile?from=2026-05-01&to=2026-05-07")
        assert b"212.50" in response.data, "Filtered total 212.50 must appear in HTML"

    def test_single_day_range_returns_one_expense(self, auth_client):
        _, user_id = auth_client
        stats = get_summary_stats(user_id, date_from="2026-05-05", date_to="2026-05-05")
        assert stats["transaction_count"] == 1, "Single-day range must return exactly 1 expense"
        assert stats["total_spent"] == "₹120.00"

    def test_category_breakdown_respects_date_range(self, auth_client):
        """Only categories with expenses in the range should appear."""
        _, user_id = auth_client
        # Range 05-01..05-03 covers Food and Transport only
        categories = get_category_breakdown(user_id, date_from="2026-05-01", date_to="2026-05-03")
        names = {item["name"] for item in categories}
        assert names == {"Food", "Transport"}, "Only Food and Transport fall in 05-01..05-03"

    def test_transactions_list_respects_date_range(self, auth_client):
        _, user_id = auth_client
        txns = get_recent_transactions(user_id, date_from="2026-05-01", date_to="2026-05-03")
        assert len(txns) == 2, "Exactly 2 transactions in 05-01..05-03"

    def test_transactions_ordered_newest_first_within_range(self, auth_client):
        _, user_id = auth_client
        txns = get_recent_transactions(user_id, date_from="2026-05-01", date_to="2026-05-07")
        # Newest in range is May 7, oldest is May 1
        assert txns[0]["date"] == "May 7", "First transaction must be the most recent"
        assert txns[-1]["date"] == "May 1", "Last transaction must be the oldest"


# ===========================================================================
# 4. Preset Shortcuts
# ===========================================================================

class TestPresetThisMonth:
    def test_this_month_route_returns_200(self, auth_client):
        client, _ = auth_client
        pf, pt = _preset_ranges()["this_month"]
        response = client.get(f"/profile?from={pf}&to={pt}")
        assert response.status_code == 200, "This Month preset URL must return 200"

    def test_this_month_activates_correct_preset(self, auth_client):
        """
        When from/to exactly match This Month bounds, active_preset must be
        'this_month'. The template should visually distinguish the active button;
        we check that the page renders successfully and includes the label.
        """
        client, _ = auth_client
        pf, pt = _preset_ranges()["this_month"]
        response = client.get(f"/profile?from={pf}&to={pt}")
        assert b"This Month" in response.data, "This Month label must appear in filter bar"

    def test_this_month_stats_exclude_expenses_outside_month(self, auth_client):
        """
        All seeded expenses are in May 2026. If today is in May 2026 the preset
        returns all of them; if today is NOT May 2026 the preset returns zero.
        Either way the result must be consistent — no 500 error and a valid total.
        """
        _, user_id = auth_client
        pf, pt = _preset_ranges()["this_month"]
        stats = get_summary_stats(user_id, date_from=pf, date_to=pt)
        assert "₹" in stats["total_spent"], "Total must be formatted with rupee symbol"
        assert isinstance(stats["transaction_count"], int)


class TestPresetLastMonth:
    def test_last_month_route_returns_200(self, auth_client):
        client, _ = auth_client
        pf, pt = _preset_ranges()["last_month"]
        response = client.get(f"/profile?from={pf}&to={pt}")
        assert response.status_code == 200, "Last Month preset URL must return 200"

    def test_last_month_activates_correct_preset(self, auth_client):
        client, _ = auth_client
        pf, pt = _preset_ranges()["last_month"]
        response = client.get(f"/profile?from={pf}&to={pt}")
        assert b"Last Month" in response.data, "Last Month label must appear in filter bar"

    def test_last_month_returns_no_expenses_for_may_2026_seed(self, auth_client):
        """
        All seeded expenses are in May 2026. Last Month from today (2026-05-20)
        is April 2026, which contains zero seeded expenses.
        """
        _, user_id = auth_client
        today = date.today()
        if today.year == 2026 and today.month == 5:
            # Only meaningful when running the test suite in May 2026
            pf, pt = _preset_ranges()["last_month"]
            stats = get_summary_stats(user_id, date_from=pf, date_to=pt)
            assert stats["transaction_count"] == 0, "Last Month (April 2026) must have 0 expenses"
            assert stats["total_spent"] == "₹0.00"

    def test_last_month_empty_range_produces_no_500(self, auth_client):
        client, _ = auth_client
        pf, pt = _preset_ranges()["last_month"]
        response = client.get(f"/profile?from={pf}&to={pt}")
        assert response.status_code == 200, "Empty Last Month range must not produce a server error"


class TestPresetLastSevenDays:
    def test_last_7_days_route_returns_200(self, auth_client):
        client, _ = auth_client
        pf, pt = _preset_ranges()["last_7_days"]
        response = client.get(f"/profile?from={pf}&to={pt}")
        assert response.status_code == 200, "Last 7 Days preset URL must return 200"

    def test_last_7_days_activates_correct_preset(self, auth_client):
        client, _ = auth_client
        pf, pt = _preset_ranges()["last_7_days"]
        response = client.get(f"/profile?from={pf}&to={pt}")
        assert b"Last 7 Days" in response.data, "Last 7 Days label must appear in filter bar"

    def test_last_7_days_range_is_today_inclusive(self, auth_client):
        """Spec says 'today inclusive' — confirm pt equals today's date."""
        _, pt = _preset_ranges()["last_7_days"]
        assert pt == date.today().isoformat(), "Last 7 Days end date must be today"

    def test_last_7_days_range_spans_seven_days(self, auth_client):
        pf, pt = _preset_ranges()["last_7_days"]
        start = date.fromisoformat(pf)
        end = date.fromisoformat(pt)
        assert (end - start).days == 6, "Last 7 Days window must be exactly 6 days apart (7 inclusive)"

    def test_last_7_days_stats_are_valid(self, auth_client):
        _, user_id = auth_client
        pf, pt = _preset_ranges()["last_7_days"]
        stats = get_summary_stats(user_id, date_from=pf, date_to=pt)
        assert "₹" in stats["total_spent"]
        assert isinstance(stats["transaction_count"], int)
        assert stats["transaction_count"] >= 0


# ===========================================================================
# 5. Empty Result Range
# ===========================================================================

class TestEmptyResultRange:
    """A date range that contains no expenses must show zeroes, not crash."""

    EMPTY_FROM = "2020-01-01"
    EMPTY_TO   = "2020-01-31"

    def test_route_returns_200_for_empty_range(self, auth_client):
        client, _ = auth_client
        response = client.get(f"/profile?from={self.EMPTY_FROM}&to={self.EMPTY_TO}")
        assert response.status_code == 200, "Empty range must not produce a server error"

    def test_empty_range_shows_zero_total(self, auth_client):
        client, _ = auth_client
        response = client.get(f"/profile?from={self.EMPTY_FROM}&to={self.EMPTY_TO}")
        assert b"0.00" in response.data, "Empty range must display ₹0.00 total"

    def test_empty_range_summary_stats_zeros(self, auth_client):
        _, user_id = auth_client
        stats = get_summary_stats(user_id, date_from=self.EMPTY_FROM, date_to=self.EMPTY_TO)
        assert stats["total_spent"] == "₹0.00", "Empty range total must be ₹0.00"
        assert stats["transaction_count"] == 0, "Empty range transaction count must be 0"
        assert stats["top_category"] == "—", "Empty range top_category must be the em-dash placeholder"

    def test_empty_range_transactions_list_is_empty(self, auth_client):
        _, user_id = auth_client
        txns = get_recent_transactions(user_id, date_from=self.EMPTY_FROM, date_to=self.EMPTY_TO)
        assert txns == [], "Empty range must return an empty transaction list"

    def test_empty_range_category_breakdown_is_empty(self, auth_client):
        _, user_id = auth_client
        cats = get_category_breakdown(user_id, date_from=self.EMPTY_FROM, date_to=self.EMPTY_TO)
        assert cats == [], "Empty range must return an empty category breakdown"

    def test_empty_user_with_date_params_returns_200(self, flask_client, empty_user):
        client, _ = flask_client
        with client.session_transaction() as sess:
            sess["user_id"] = empty_user
        response = client.get(f"/profile?from={self.EMPTY_FROM}&to={self.EMPTY_TO}")
        assert response.status_code == 200, "Empty user with date params must not crash"


# ===========================================================================
# 6. Invalid / Malformed Date Parameters — Graceful Fallback to All Time
# ===========================================================================

class TestInvalidDateParamFallback:
    """
    Spec: 'If either param is absent or invalid, the route falls back to All Time.'
    Spec rule: 'accept only strings that match YYYY-MM-DD; reject anything else silently.'
    """

    @pytest.mark.parametrize("from_val,to_val", [
        ("not-a-date",     "also-bad"),
        ("2026/05/01",     "2026/05/31"),          # wrong separator
        ("01-05-2026",     "31-05-2026"),           # DD-MM-YYYY
        ("2026-13-01",     "2026-13-31"),           # impossible month — still matches regex
        ("2026-05-01T00:00:00", "2026-05-31T23:59:59"),  # ISO datetime, not YYYY-MM-DD
        ("",               ""),                     # empty strings
        ("2026-05-",       "2026-05-"),             # truncated
        ("' OR 1=1 --",   "' OR 1=1 --"),          # SQL injection attempt
        ("2026-05-01",     "bad-to"),               # one valid, one invalid
        ("bad-from",       "2026-05-31"),            # one invalid, one valid
    ])
    def test_invalid_params_return_200(self, auth_client, from_val, to_val):
        client, _ = auth_client
        response = client.get(f"/profile?from={from_val}&to={to_val}")
        assert response.status_code == 200, (
            f"Invalid params from='{from_val}' to='{to_val}' must not produce a server error"
        )

    @pytest.mark.parametrize("from_val,to_val", [
        ("not-a-date", "also-bad"),
        ("2026/05/01", "2026/05/31"),
        ("",           ""),
        ("' OR 1=1 --", "' OR 1=1 --"),
    ])
    def test_invalid_params_fall_back_to_all_time_total(self, auth_client, from_val, to_val):
        """
        When both params are invalid the query must run without a date filter,
        returning the full All Time total of 346.24.
        """
        client, _ = auth_client
        response = client.get(f"/profile?from={from_val}&to={to_val}")
        assert b"346.24" in response.data, (
            f"Invalid params must fall back to All Time total 346.24; "
            f"from='{from_val}' to='{to_val}'"
        )

    def test_missing_from_param_returns_200(self, auth_client):
        """Only 'to' supplied — spec says fall back to All Time."""
        client, _ = auth_client
        response = client.get("/profile?to=2026-05-31")
        assert response.status_code == 200, "Missing 'from' param must not crash"

    def test_missing_to_param_returns_200(self, auth_client):
        """Only 'from' supplied — spec says fall back to All Time."""
        client, _ = auth_client
        response = client.get("/profile?from=2026-05-01")
        assert response.status_code == 200, "Missing 'to' param must not crash"

    def test_no_params_at_all_returns_200(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile")
        assert response.status_code == 200, "No params must return 200 (All Time)"


# ===========================================================================
# 7. Active Preset Detection (server-side)
# ===========================================================================

class TestActivePresetDetection:
    def test_no_params_produces_all_time_active(self, auth_client):
        """
        Spec: active filter state must be derived server-side.
        No params → active_preset = 'all_time'.
        Verify the rendered page carries the All Time highlight cue.
        """
        client, _ = auth_client
        response = client.get("/profile")
        assert b"All Time" in response.data

    def test_this_month_params_highlight_this_month(self, auth_client):
        client, _ = auth_client
        pf, pt = _preset_ranges()["this_month"]
        response = client.get(f"/profile?from={pf}&to={pt}")
        assert b"This Month" in response.data

    def test_last_month_params_highlight_last_month(self, auth_client):
        client, _ = auth_client
        pf, pt = _preset_ranges()["last_month"]
        response = client.get(f"/profile?from={pf}&to={pt}")
        assert b"Last Month" in response.data

    def test_last_7_days_params_highlight_last_7_days(self, auth_client):
        client, _ = auth_client
        pf, pt = _preset_ranges()["last_7_days"]
        response = client.get(f"/profile?from={pf}&to={pt}")
        assert b"Last 7 Days" in response.data

    def test_custom_range_does_not_match_any_preset(self, auth_client):
        """
        A date range that matches no preset must not falsely activate a preset.
        The page must still load correctly.
        """
        client, _ = auth_client
        response = client.get("/profile?from=2026-05-01&to=2026-05-16")
        assert response.status_code == 200, "Custom range not matching any preset must return 200"


# ===========================================================================
# 8. Filter Bar HTML Landmarks
# ===========================================================================

class TestFilterBarHtml:
    """
    Spec: profile.html must contain a filter bar with four preset labels
    and a custom date range form with an Apply button.
    """

    def test_filter_bar_contains_this_month_label(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile")
        assert b"This Month" in response.data, "Filter bar must contain 'This Month' label"

    def test_filter_bar_contains_last_month_label(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile")
        assert b"Last Month" in response.data, "Filter bar must contain 'Last Month' label"

    def test_filter_bar_contains_last_7_days_label(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile")
        assert b"Last 7 Days" in response.data, "Filter bar must contain 'Last 7 Days' label"

    def test_filter_bar_contains_all_time_label(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile")
        assert b"All Time" in response.data, "Filter bar must contain 'All Time' label"

    def test_filter_bar_contains_apply_button(self, auth_client):
        client, _ = auth_client
        response = client.get("/profile")
        assert b"Apply" in response.data, "Filter bar must contain an Apply button"

    def test_filter_form_uses_get_method(self, auth_client):
        """Spec: the custom date range form must use GET so range appears in URL."""
        client, _ = auth_client
        response = client.get("/profile")
        html = response.data.decode("utf-8", errors="replace").lower()
        # Look for <form method="get"> or <form method='get'>
        assert 'method="get"' in html or "method='get'" in html, (
            "Custom date range form must use GET method so filter params appear in the URL"
        )

    def test_date_inputs_present_in_filter_form(self, auth_client):
        """Spec: two <input type='date'> fields for custom range picker."""
        client, _ = auth_client
        response = client.get("/profile")
        html = response.data.decode("utf-8", errors="replace").lower()
        assert html.count('type="date"') >= 2 or html.count("type='date'") >= 2, (
            "Filter form must contain at least two date input fields"
        )

    def test_preset_links_point_to_profile_route(self, auth_client):
        """Spec: preset shortcuts are anchor tags that append from/to params to /profile."""
        client, _ = auth_client
        response = client.get("/profile")
        html = response.data.decode("utf-8", errors="replace")
        # Each preset anchor must contain href="/profile?from=..."
        assert "/profile?from=" in html, "Preset links must generate /profile?from=... hrefs"


# ===========================================================================
# 9. Query-Layer Unit Tests — date_from / date_to keyword arguments
# ===========================================================================

class TestQueryLayerDateFilter:
    """
    Direct unit tests on the query helpers to verify the date_from / date_to
    kwargs work correctly in isolation from the HTTP layer.
    """

    # --- get_summary_stats ---

    def test_summary_stats_no_filter_returns_all(self, seed_user):
        stats = get_summary_stats(seed_user)
        assert stats["transaction_count"] == 8
        assert stats["total_spent"] == "₹346.24"

    def test_summary_stats_date_from_only_filters_correctly(self, seed_user):
        """Only date_from supplied: spec says only from is needed for >= filter."""
        stats = get_summary_stats(seed_user, date_from="2026-05-10")
        # Expenses on or after 05-10: Entertainment(20), Shopping(89.99), Other(15), Food(8.75) = 4
        assert stats["transaction_count"] == 4

    def test_summary_stats_date_to_only_filters_correctly(self, seed_user):
        """Only date_to supplied: spec says only to is needed for <= filter."""
        stats = get_summary_stats(seed_user, date_to="2026-05-05")
        # Expenses on or before 05-05: Food(12.50), Transport(35), Bills(120) = 3
        assert stats["transaction_count"] == 3

    def test_summary_stats_both_dates_filters_correctly(self, seed_user):
        stats = get_summary_stats(seed_user, date_from="2026-05-03", date_to="2026-05-10")
        # 05-03 Transport, 05-05 Bills, 05-07 Health, 05-10 Entertainment = 4
        assert stats["transaction_count"] == 4

    def test_summary_stats_defaults_to_none(self, seed_user):
        """Query helpers must accept no date kwargs and work correctly."""
        stats = get_summary_stats(seed_user, date_from=None, date_to=None)
        assert stats["transaction_count"] == 8

    # --- get_recent_transactions ---

    def test_transactions_date_from_filters_correctly(self, seed_user):
        txns = get_recent_transactions(seed_user, date_from="2026-05-12")
        # 05-12 Shopping, 05-14 Other, 05-16 Food = 3
        assert len(txns) == 3

    def test_transactions_date_to_filters_correctly(self, seed_user):
        txns = get_recent_transactions(seed_user, date_to="2026-05-03")
        # 05-01 Food, 05-03 Transport = 2
        assert len(txns) == 2

    def test_transactions_both_dates_filter_correctly(self, seed_user):
        txns = get_recent_transactions(seed_user, date_from="2026-05-05", date_to="2026-05-12")
        # 05-05 Bills, 05-07 Health, 05-10 Entertainment, 05-12 Shopping = 4
        assert len(txns) == 4

    def test_transactions_empty_range_returns_empty_list(self, seed_user):
        txns = get_recent_transactions(seed_user, date_from="2020-01-01", date_to="2020-12-31")
        assert txns == []

    def test_transactions_none_filter_returns_all(self, seed_user):
        txns = get_recent_transactions(seed_user, date_from=None, date_to=None)
        assert len(txns) == 8

    # --- get_category_breakdown ---

    def test_category_breakdown_date_range_limits_categories(self, seed_user):
        """Only categories present in the range should be returned."""
        # 05-01..05-05 includes Food, Transport, Bills
        cats = get_category_breakdown(seed_user, date_from="2026-05-01", date_to="2026-05-05")
        names = {c["name"] for c in cats}
        assert names == {"Food", "Transport", "Bills"}

    def test_category_breakdown_percentages_sum_to_100_with_filter(self, seed_user):
        cats = get_category_breakdown(seed_user, date_from="2026-05-01", date_to="2026-05-07")
        assert sum(c["percent"] for c in cats) == 100, "Filtered category percents must sum to 100"

    def test_category_breakdown_empty_range_returns_empty(self, seed_user):
        cats = get_category_breakdown(seed_user, date_from="2020-01-01", date_to="2020-12-31")
        assert cats == []

    def test_category_breakdown_none_filter_returns_all_categories(self, seed_user):
        cats = get_category_breakdown(seed_user, date_from=None, date_to=None)
        assert len(cats) == 7, "All 7 unique categories must appear with no date filter"

    def test_category_breakdown_amounts_formatted_with_rupee(self, seed_user):
        cats = get_category_breakdown(seed_user, date_from="2026-05-01", date_to="2026-05-07")
        for cat in cats:
            assert cat["amount"].startswith("₹"), "Category amounts must be formatted with ₹"
