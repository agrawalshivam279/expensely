import sqlite3
import re
from datetime import date, datetime, timedelta
from calendar import monthrange
from flask import Flask, render_template, session, request, redirect, url_for, abort
from werkzeug.security import check_password_hash, generate_password_hash
from database.db import get_db, init_db, seed_db
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
    add_expense as insert_expense,
    get_expense_by_id,
    update_expense,
)

CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]

app = Flask(__name__)
app.secret_key = "spendly-dev-secret"

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect("/")

    if request.method == "GET":
        return render_template("register.html")

    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]
    confirm_password = request.form["confirm_password"]

    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters")
    if password != confirm_password:
        return render_template("register.html", error="Passwords do not match")

    password_hash = generate_password_hash(password)
    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        return render_template("register.html", error="An account with that email already exists")
    db.close()
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect("/")

    if request.method == "GET":
        return render_template("login.html")

    email = request.form["email"]
    password = request.form["password"]

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    db.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password")

    session["user_id"] = user["id"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date_param(value):
    if value and _DATE_RE.match(value):
        return value
    return None


def _preset_ranges():
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


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    date_from = _parse_date_param(request.args.get("from"))
    date_to   = _parse_date_param(request.args.get("to"))

    presets = _preset_ranges()
    active_preset = None
    for name, (pf, pt) in presets.items():
        if date_from == pf and date_to == pt:
            active_preset = name
            break
    if date_from is None and date_to is None:
        active_preset = "all_time"

    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    stats = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    transactions = get_recent_transactions(user_id, date_from=date_from, date_to=date_to)
    categories = get_category_breakdown(user_id, date_from=date_from, date_to=date_to)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        date_from=date_from,
        date_to=date_to,
        active_preset=active_preset,
        presets=presets,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("add_expense.html", categories=CATEGORIES)

    amount_raw  = request.form.get("amount", "").strip()
    category    = request.form.get("category", "").strip()
    date_val    = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip() or None

    error = None
    amount = None
    try:
        amount = float(amount_raw)
        if amount <= 0:
            error = "Amount must be greater than zero"
    except ValueError:
        error = "Amount must be a valid number"

    if not error and category not in CATEGORIES:
        error = "Invalid category selected"

    if not error:
        if not _DATE_RE.match(date_val):
            error = "Date must be in YYYY-MM-DD format"
        else:
            try:
                parsed = datetime.strptime(date_val, "%Y-%m-%d").date()
                if parsed > date.today():
                    error = "Date cannot be in the future"
            except ValueError:
                error = "Date must be in YYYY-MM-DD format"

    if error:
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            error=error,
            form={"amount": amount_raw, "category": category,
                  "date": date_val, "description": description or ""},
        )

    insert_expense(session["user_id"], amount, category, date_val, description)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "GET":
        return render_template("edit_expense.html", categories=CATEGORIES, form=expense)

    amount_raw  = request.form.get("amount", "").strip()
    category    = request.form.get("category", "").strip()
    date_val    = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip() or None

    error = None
    amount = None
    try:
        amount = float(amount_raw)
        if amount <= 0:
            error = "Amount must be greater than zero"
    except ValueError:
        error = "Amount must be a valid number"

    if not error and category not in CATEGORIES:
        error = "Invalid category selected"

    if not error:
        if not _DATE_RE.match(date_val):
            error = "Date must be in YYYY-MM-DD format"
        else:
            try:
                parsed = datetime.strptime(date_val, "%Y-%m-%d").date()
                if parsed > date.today():
                    error = "Date cannot be in the future"
            except ValueError:
                error = "Date must be in YYYY-MM-DD format"

    if error:
        return render_template(
            "edit_expense.html",
            categories=CATEGORIES,
            error=error,
            form={"amount": amount_raw, "category": category,
                  "date": date_val, "description": description or ""},
        )

    update_expense(id, user_id, amount, category, date_val, description)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
