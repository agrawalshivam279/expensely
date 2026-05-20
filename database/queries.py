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


def get_summary_stats(user_id):
    db = get_db()
    try:
        row = db.execute(
            "SELECT SUM(amount) AS total, COUNT(*) AS cnt FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        total = row["total"] or 0.0
        count = row["cnt"] or 0
        top_row = db.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return {
            "total_spent": f"₹{total:.2f}",
            "transaction_count": count,
            "top_category": top_row["category"] if top_row else "—",
        }
    finally:
        db.close()


def get_recent_transactions(user_id, limit=10):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT date, description, category, amount "
            "FROM expenses WHERE user_id = ? ORDER BY date DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        result = []
        for row in rows:
            parsed = datetime.strptime(row["date"], "%Y-%m-%d")
            result.append({
                "date": f"{parsed.strftime('%b')} {parsed.day}",
                "description": row["description"] or "",
                "category": row["category"],
                "amount": f"₹{row['amount']:.2f}",
            })
        return result
    finally:
        db.close()


def get_category_breakdown(user_id):
    db = get_db()
    try:
        rows = db.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ? GROUP BY category ORDER BY total DESC",
            (user_id,),
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
