from datetime import datetime
from database.db import get_db


def get_user_by_id(user_id):
    db = get_db()
    try:
        row = db.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        created = datetime.strptime(row["created_at"][:19], "%Y-%m-%d %H:%M:%S")
        name = row["name"]
        parts = name.split()
        initials = (parts[0][0] + parts[-1][0]).upper() if len(parts) >= 2 else parts[0][0].upper()
        return {
            "name": name,
            "email": row["email"],
            "initials": initials,
            "member_since": created.strftime("%B %Y"),
        }
    finally:
        db.close()


def _date_clause(date_from, date_to):
    """Return (sql_fragment, params) for an optional date range filter."""
    if date_from and date_to:
        return " AND date BETWEEN ? AND ?", (date_from, date_to)
    if date_from:
        return " AND date >= ?", (date_from,)
    if date_to:
        return " AND date <= ?", (date_to,)
    return "", ()


def get_summary_stats(user_id, date_from=None, date_to=None):
    db = get_db()
    try:
        date_sql, date_params = _date_clause(date_from, date_to)
        row = db.execute(
            f"SELECT SUM(amount) AS total, COUNT(*) AS cnt FROM expenses WHERE user_id = ?{date_sql}",
            (user_id, *date_params),
        ).fetchone()
        total = row["total"] or 0.0
        count = row["cnt"] or 0
        top_row = db.execute(
            f"SELECT category FROM expenses WHERE user_id = ?{date_sql} "
            "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id, *date_params),
        ).fetchone()
        return {
            "total_spent": f"₹{total:.2f}",
            "transaction_count": count,
            "top_category": top_row["category"] if top_row else "—",
        }
    finally:
        db.close()


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    db = get_db()
    try:
        date_sql, date_params = _date_clause(date_from, date_to)
        rows = db.execute(
            f"SELECT id, date, description, category, amount "
            f"FROM expenses WHERE user_id = ?{date_sql} ORDER BY date DESC LIMIT ?",
            (user_id, *date_params, limit),
        ).fetchall()
        result = []
        for row in rows:
            parsed = datetime.strptime(row["date"], "%Y-%m-%d")
            result.append({
                "id": row["id"],
                "date": f"{parsed.strftime('%b')} {parsed.day}",
                "description": row["description"] or "",
                "category": row["category"],
                "amount": f"₹{row['amount']:.2f}",
            })
        return result
    finally:
        db.close()


def get_category_breakdown(user_id, date_from=None, date_to=None):
    db = get_db()
    try:
        date_sql, date_params = _date_clause(date_from, date_to)
        rows = db.execute(
            f"SELECT category, SUM(amount) AS total FROM expenses "
            f"WHERE user_id = ?{date_sql} GROUP BY category ORDER BY total DESC",
            (user_id, *date_params),
        ).fetchall()
        if not rows:
            return []
        grand_total = sum(row["total"] for row in rows)
        breakdown = [
            {
                "name": row["category"],
                "amount": f"₹{row['total']:.2f}",
                "percent": round(row["total"] / grand_total * 100),
                "_raw": row["total"],
            }
            for row in rows
        ]
        diff = 100 - sum(item["percent"] for item in breakdown)
        if diff != 0:
            breakdown[0]["percent"] += diff
        for item in breakdown:
            del item["_raw"]
        return breakdown
    finally:
        db.close()


def get_expense_by_id(expense_id, user_id):
    db = get_db()
    try:
        return db.execute(
            "SELECT id, amount, category, date, description "
            "FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
    finally:
        db.close()


def update_expense(expense_id, user_id, amount, category, date, description):
    db = get_db()
    try:
        db.execute(
            "UPDATE expenses SET amount=?, category=?, date=?, description=? "
            "WHERE id=? AND user_id=?",
            (amount, category, date, description or None, expense_id, user_id),
        )
        db.commit()
    finally:
        db.close()


def add_expense(user_id, amount, category, date, description):
    db = get_db()
    try:
        db.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description)"
            " VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description or None),
        )
        db.commit()
    finally:
        db.close()
