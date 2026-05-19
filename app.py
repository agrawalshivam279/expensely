import sqlite3
from flask import Flask, render_template, session, request, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from database.db import get_db, init_db, seed_db

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


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "January 2026",
    }
    stats = {
        "total_spent": "₹346.24",
        "transaction_count": 8,
        "top_category": "Bills",
    }
    transactions = [
        {"date": "May 16", "description": "Coffee and snacks",  "category": "Food",          "amount": "₹8.75"},
        {"date": "May 14", "description": "Miscellaneous",       "category": "Other",         "amount": "₹15.00"},
        {"date": "May 12", "description": "New shoes",           "category": "Shopping",      "amount": "₹89.99"},
        {"date": "May 10", "description": "Movie tickets",       "category": "Entertainment", "amount": "₹20.00"},
        {"date": "May 07", "description": "Pharmacy",            "category": "Health",        "amount": "₹45.00"},
        {"date": "May 05", "description": "Electricity bill",    "category": "Bills",         "amount": "₹120.00"},
        {"date": "May 03", "description": "Monthly bus pass",    "category": "Transport",     "amount": "₹35.00"},
        {"date": "May 01", "description": "Lunch at café",       "category": "Food",          "amount": "₹12.50"},
    ]
    categories = [
        {"name": "Bills",         "amount": "₹120.00", "percent": 35},
        {"name": "Shopping",      "amount": "₹89.99",  "percent": 26},
        {"name": "Health",        "amount": "₹45.00",  "percent": 13},
        {"name": "Transport",     "amount": "₹35.00",  "percent": 10},
        {"name": "Entertainment", "amount": "₹20.00",  "percent": 6},
        {"name": "Food",          "amount": "₹21.25",  "percent": 6},
        {"name": "Other",         "amount": "₹15.00",  "percent": 4},
    ]
    return render_template("profile.html", user=user, stats=stats,
                           transactions=transactions, categories=categories)


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
