"""
Shifts Management Module
Controls opening and closing cashier shifts, operational cash balances,
sales reconciliation, and barista accountability summaries.
"""
import datetime
import logging
import math
from app.core.database import get_db, dict_from_row
from app.core.audit import log_business_action

logger = logging.getLogger(__name__)

def get_active_shift(branch_id: int = 1) -> dict | None:
    """Retrieve the currently open shift for the branch, if any."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*, u.full_name as barista_name, u.username
            FROM shifts s
            JOIN users u ON s.user_id = u.id
            WHERE (s.branch_id = ? OR s.branch_id IS NULL) AND s.status = 'open'
            ORDER BY s.id DESC LIMIT 1
            """,
            (branch_id,),
        )
        row = cursor.fetchone()
        return dict_from_row(row)

def open_shift(current_user: dict, opening_cash: float, notes: str = "", ip_address: str = None) -> tuple[dict | None, str]:
    """Open a new cashier/operational shift."""
    if not math.isfinite(opening_cash) or opening_cash < 0:
        return None, "İlkin kassa məbləği düzgün deyil."
    branch_id = current_user.get("branch_id", 1)
    user_id = current_user["id"]

    existing = get_active_shift(branch_id)
    if existing:
        return None, f"Hal-hazırda artıq açıq növbə mövcuddur (Açan: {existing['barista_name']}). Əvvəlcə onu bağlayın."

    opened_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO shifts (branch_id, user_id, opened_at, opening_cash, notes, status)
            VALUES (?, ?, ?, ?, ?, 'open')
            """,
            (branch_id, user_id, opened_at, float(opening_cash), notes),
        )
        shift_id = cursor.lastrowid

    log_business_action(
        user_id=user_id,
        username=current_user["username"],
        role=current_user["role"],
        action="open_shift",
        entity_type="shifts",
        entity_id=shift_id,
        details=f"Növbə açıldı: İlkin kassa qalığı {opening_cash:.2f} AZN",
        ip_address=ip_address,
    )

    return get_shift_details(shift_id), "Növbə uğurla açıldı."

def get_shift_details(shift_id: int) -> dict | None:
    """Get full details and current calculated metrics for a shift."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*, u.full_name as barista_name, u.username
            FROM shifts s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ?
            """,
            (shift_id,),
        )
        shift = cursor.fetchone()
        if not shift:
            return None

        res = dict_from_row(shift)

        # Calculate sales in this shift
        cursor.execute(
            """
            SELECT count(*) as total_orders,
                   sum(CASE WHEN status = 'completed' THEN final_amount ELSE 0 END) as total_revenue,
                   sum(CASE WHEN status = 'completed' AND payment_method = 'cash' THEN final_amount ELSE 0 END) as cash_revenue,
                   sum(CASE WHEN status = 'completed' AND payment_method = 'card' THEN final_amount ELSE 0 END) as card_revenue,
                   sum(CASE WHEN status = 'completed' AND payment_method NOT IN ('cash', 'card') THEN final_amount ELSE 0 END) as other_revenue,
                   sum(CASE WHEN status = 'completed' THEN (total_amount - final_amount) ELSE 0 END) as total_discounts,
                   sum(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled_orders_count
            FROM orders
            WHERE shift_id = ?
            """,
            (shift_id,),
        )
        metrics = dict_from_row(cursor.fetchone())
        metrics["total_revenue"] = round(metrics.get("total_revenue") or 0.0, 2)
        metrics["cash_revenue"] = round(metrics.get("cash_revenue") or 0.0, 2)
        metrics["card_revenue"] = round(metrics.get("card_revenue") or 0.0, 2)
        metrics["other_revenue"] = round(metrics.get("other_revenue") or 0.0, 2)
        metrics["total_discounts"] = round(metrics.get("total_discounts") or 0.0, 2)
        movement = cursor.execute(
            """SELECT COALESCE(SUM(CASE WHEN direction='in' THEN amount ELSE -amount END), 0)
               AS net FROM cash_movements WHERE shift_id = ?""", (shift_id,)
        ).fetchone()
        metrics["cash_movements_net"] = round(float(movement["net"] or 0), 2)
        metrics["expected_cash"] = round(
            res["opening_cash"] + metrics["cash_revenue"] + metrics["cash_movements_net"], 2
        )

        res["metrics"] = metrics
        return res

def close_shift(current_user: dict, shift_id: int, closing_cash: float, notes: str = "", ip_address: str = None) -> tuple[dict | None, str]:
    """Close an active shift, calculate cash balance discrepancy, and save final summary."""
    if not math.isfinite(closing_cash) or closing_cash < 0:
        return None, "Yekun kassa məbləği düzgün deyil."
    shift = get_shift_details(shift_id)
    if not shift:
        return None, "Növbə tapılmadı."

    if shift["status"] == "closed":
        return None, "Bu növbə artıq bağlanmışdır."
    if current_user.get("role") != "developer" and shift["branch_id"] != current_user.get("branch_id", 1):
        return None, "Bu növbə sizin filialınıza aid deyil."

    expected_cash = shift["metrics"]["expected_cash"]
    cash_difference = round(closing_cash - expected_cash, 2)
    closed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    full_notes = notes
    if cash_difference != 0:
        diff_note = f" [Kassa fərqi: {cash_difference:+.2f} AZN]"
        full_notes = (notes + diff_note).strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE shifts
            SET closed_at = ?, closing_cash = ?, expected_cash = ?, cash_difference = ?, notes = ?, status = 'closed'
            WHERE id = ?
            """,
            (closed_at, float(closing_cash), expected_cash, cash_difference, full_notes, shift_id),
        )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="close_shift",
        entity_type="shifts",
        entity_id=shift_id,
        details=f"Növbə bağlandı: Faktiki kassa: {closing_cash:.2f} AZN, Gözlənilən: {expected_cash:.2f} AZN (Fərq: {cash_difference:+.2f} AZN)",
        ip_address=ip_address,
    )

    return get_shift_details(shift_id), "Növbə uğurla bağlandı."

def auto_close_forgotten_shifts(now=None, ip_address=None) -> int:
    """Close open shifts that belong to a previous calendar day.

    The operation is deliberately idempotent: the update is restricted to
    open rows, so a scheduler retry cannot close or audit a shift twice.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now.astimezone(datetime.timezone.utc).date().isoformat()
    closed_count = 0
    audit_rows = []
    try:
        with get_db() as conn:
            rows = conn.execute(
                """SELECT s.id, s.expected_cash, s.branch_id, s.user_id,
                          u.username, u.role
                   FROM shifts s JOIN users u ON u.id = s.user_id
                   WHERE s.status = 'open' AND date(s.opened_at) < date(?)""",
                (cutoff,),
            ).fetchall()
            closed_at = now.isoformat()
            note = "Otomatik kapatıldı – Gece yarısı itibarıyla kapatılmamış növbe"
            for row in rows:
                cursor = conn.execute(
                    """UPDATE shifts
                       SET closed_at = ?, closing_cash = expected_cash,
                           expected_cash = expected_cash, cash_difference = 0,
                           notes = ?, status = 'closed'
                       WHERE id = ? AND status = 'open'""",
                    (closed_at, note, row["id"]),
                )
                if cursor.rowcount:
                    closed_count += 1
                    audit_rows.append(row)
        for row in audit_rows:
            try:
                log_business_action(
                    user_id=row["user_id"],
                    username=row["username"],
                    role=row["role"],
                    action="auto_close_shift",
                    entity_type="shifts",
                    entity_id=row["id"],
                    details=note,
                    ip_address=ip_address,
                )
            except Exception:
                logger.exception("Failed to audit auto-closed shift %s", row["id"])
    except Exception:
        logger.exception("Automatic forgotten-shift closure failed")
    return closed_count

def list_shifts(branch_id: int = 1, limit: int = 30) -> list[dict]:
    """List historical shifts with summary metrics."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.*, u.full_name as barista_name, u.username,
                   (SELECT count(*) FROM orders WHERE shift_id = s.id AND status = 'completed') as order_count,
                   (SELECT coalesce(sum(final_amount), 0) FROM orders WHERE shift_id = s.id AND status = 'completed') as total_revenue
            FROM shifts s
            JOIN users u ON s.user_id = u.id
            WHERE (s.branch_id = ? OR s.branch_id IS NULL)
            ORDER BY s.id DESC LIMIT ?
            """,
            (branch_id, limit),
        )
        return [dict_from_row(r) for r in cursor.fetchall()]
