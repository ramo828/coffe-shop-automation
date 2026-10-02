"""Till/cash movement ledger and reconciliation helpers."""
import math
from datetime import datetime, timedelta

from app.core.database import get_db, dict_from_row
from app.core.audit import log_business_action


VALID_DIRECTIONS = {"in", "out"}


def create_cash_movement(current_user, data, ip_address=None):
    """Record an operational till movement, independent of sales revenue."""
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        return None, "Məbləğ düzgün deyil."
    direction = str(data.get("direction", data.get("type", ""))).lower().strip()
    if direction not in VALID_DIRECTIONS or not math.isfinite(amount) or amount <= 0:
        return None, "İstiqamət in/out və müsbət məbləğ tələb olunur."

    branch_id = current_user.get("branch_id", 1)
    shift_id = data.get("shift_id")
    debt_value = data.get("is_debt", data.get("debt_flag", data.get("debt", False)))
    if isinstance(debt_value, str):
        debt_value = debt_value.lower().strip() in {"1", "true", "yes", "on"}
    is_debt = 1 if debt_value else 0
    related_debt = data.get("related_debt", data.get("related_debt_id"))
    reason = str(data.get("reason", "") or "").strip()
    debt_payment_value = data.get("is_debt_payment", False)
    if isinstance(debt_payment_value, str):
        debt_payment_value = debt_payment_value.lower().strip() in {"1", "true", "yes", "on"}
    is_debt_payment = 1 if debt_payment_value else 0
    note = str(data.get("note", data.get("notes", "")) or "").strip()

    with get_db() as conn:
        if shift_id is None:
            row = conn.execute(
                "SELECT id FROM shifts WHERE branch_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
                (branch_id,),
            ).fetchone()
            shift_id = row["id"] if row else None
        elif conn.execute(
            "SELECT id FROM shifts WHERE id = ? AND (branch_id = ? OR branch_id IS NULL)",
            (shift_id, branch_id),
        ).fetchone() is None and current_user.get("role") != "developer":
            return None, "Növbə sizin filialınıza aid deyil."

        cur = conn.execute(
            """INSERT INTO cash_movements
               (branch_id, shift_id, user_id, direction, amount, is_debt, is_debt_payment, related_debt, reason, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (branch_id, shift_id, current_user["id"], direction, round(amount, 2),
             is_debt, is_debt_payment, str(related_debt) if related_debt is not None else None, reason, note),
        )
        movement_id = cur.lastrowid

    log_business_action(
        current_user["id"], current_user["username"], current_user["role"],
        "create_cash_movement", "cash_movements", movement_id,
        {"direction": direction, "amount": round(amount, 2), "is_debt": bool(is_debt),
         "related_debt": related_debt, "shift_id": shift_id, "note": note},
        branch_id, ip_address,
    )
    return get_cash_movement(movement_id), "Kassa hərəkəti qeydə alındı."


def get_cash_movement(movement_id):
    with get_db() as conn:
        row = conn.execute(
            """SELECT m.*, u.username, u.full_name AS user_name
               FROM cash_movements m JOIN users u ON u.id = m.user_id WHERE m.id = ?""",
            (movement_id,),
        ).fetchone()
        return dict_from_row(row)


def list_cash_movements(branch_id=1, start=None, end=None, shift_id=None, limit=200):
    clauses, params = ["(m.branch_id = ? OR m.branch_id IS NULL)"], [branch_id]
    if start:
        clauses.append("m.created_at >= ?")
        params.append(start)
    if end:
        clauses.append("m.created_at < ?")
        params.append(end)
    if shift_id is not None:
        clauses.append("m.shift_id = ?")
        params.append(shift_id)
    params.append(max(1, min(int(limit), 1000)))
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT m.*, u.username, u.full_name AS user_name
                FROM cash_movements m JOIN users u ON u.id = m.user_id
                WHERE {' AND '.join(clauses)}
                ORDER BY m.created_at DESC, m.id DESC LIMIT ?""",
            params,
        ).fetchall()
        return [dict_from_row(row) for row in rows]


def cash_movement_totals(conn, branch_id, start, end):
    row = conn.execute(
        """SELECT COALESCE(SUM(CASE WHEN direction='in' THEN amount ELSE 0 END), 0) AS cash_in,
                  COALESCE(SUM(CASE WHEN direction='out' THEN amount ELSE 0 END), 0) AS cash_out,
                  COALESCE(SUM(CASE WHEN direction='out' AND is_debt = 1 THEN amount ELSE 0 END), 0) AS debt_out,
                  COALESCE(SUM(CASE WHEN direction='in' AND is_debt_payment = 1 THEN amount ELSE 0 END), 0) AS debt_payment_in
           FROM cash_movements
           WHERE (branch_id = ? OR branch_id IS NULL) AND created_at >= ? AND created_at < ?""",
        (branch_id, start, end),
    ).fetchone()
    return {
        "cash_in": round(float(row["cash_in"]), 2),
        "cash_out": round(float(row["cash_out"]), 2),
        "debt_out": round(float(row["debt_out"]), 2),
        "debt_payment_in": round(float(row["debt_payment_in"]), 2),
    }
