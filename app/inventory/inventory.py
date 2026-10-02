"""
Inventory Count Sessions Module
Facilitates physical stock auditing, automated variance detection (waste/spillage),
and reconciles actual counted quantities into the stock ledger with audit trails.
"""
import logging
import math
from app.core.database import get_db, dict_from_row
from app.core.audit import log_business_action

logger = logging.getLogger(__name__)

def start_inventory_session(current_user: dict, notes: str = "", ip_address: str = None) -> tuple[dict | None, str]:
    """Initialize a new stock counting session capturing a snapshot of system quantities."""
    branch_id = current_user.get("branch_id", 1)
    user_id = current_user["id"]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO inventory_counts (branch_id, user_id, status, notes)
            VALUES (?, ?, 'draft', ?)
            """,
            (branch_id, user_id, notes),
        )
        count_id = cursor.lastrowid

        # Populate snapshot from active raw materials
        cursor.execute("SELECT id, current_stock FROM raw_materials WHERE is_active = 1 AND (branch_id = ? OR branch_id IS NULL)", (branch_id,))
        materials = cursor.fetchall()

        for m in materials:
            sys_qty = round(float(m["current_stock"]), 3)
            cursor.execute(
                """
                INSERT INTO inventory_count_items (count_id, raw_material_id, system_quantity, counted_quantity, variance, notes)
                VALUES (?, ?, ?, ?, 0.0, '')
                """,
                (count_id, m["id"], sys_qty, sys_qty),
            )

    log_business_action(
        user_id=user_id,
        username=current_user["username"],
        role=current_user["role"],
        action="start_inventory_count",
        entity_type="inventory_counts",
        entity_id=count_id,
        details=f"İnventarizasiya sessiyası başlandı (#{count_id})",
        ip_address=ip_address,
    )

    return get_inventory_session(count_id), "İnventarizasiya sessiyası açıldı."

def get_inventory_session(count_id: int) -> dict | None:
    """Retrieve full details of an inventory count session including all items."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.*, u.full_name as auditor_name, u.username
            FROM inventory_counts c
            JOIN users u ON c.user_id = u.id
            WHERE c.id = ?
            """,
            (count_id,),
        )
        session = cursor.fetchone()
        if not session:
            return None

        res = dict_from_row(session)

        cursor.execute(
            """
            SELECT i.*, m.name as material_name, m.category as material_category, m.unit as material_unit
            FROM inventory_count_items i
            JOIN raw_materials m ON i.raw_material_id = m.id
            WHERE i.count_id = ?
            ORDER BY m.category ASC, m.name ASC
            """,
            (count_id,),
        )
        res["items"] = [dict_from_row(r) for r in cursor.fetchall()]
        return res

def update_inventory_counts(current_user: dict, count_id: int, items_data: list[dict]) -> tuple[bool, str]:
    """Save counted quantities entered by staff while session is still in draft."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, branch_id FROM inventory_counts WHERE id = ?", (count_id,))
        row = cursor.fetchone()
        if not row:
            return False, "Sessiya tapılmadı."
        if row["status"] != "draft":
            return False, "Yalnız qaralama statusunda olan sayım yenilənə bilər."
        if current_user.get("role") != "developer" and row["branch_id"] != current_user.get("branch_id", 1):
            return False, "Bu inventarizasiya sizin filialınıza aid deyil."

        for itm in items_data:
            item_id = itm.get("id")
            try:
                counted_qty = float(itm.get("counted_quantity", 0.0))
            except (TypeError, ValueError):
                return False, "Sayılmış miqdar düzgün deyil."
            if not math.isfinite(counted_qty) or counted_qty < 0:
                return False, "Sayılmış miqdar düzgün deyil."
            notes = str(itm.get("notes", ""))

            cursor.execute("SELECT system_quantity FROM inventory_count_items WHERE id = ? AND count_id = ?", (item_id, count_id))
            sys_row = cursor.fetchone()
            if sys_row:
                variance = round(counted_qty - sys_row["system_quantity"], 3)
                cursor.execute(
                    """
                    UPDATE inventory_count_items
                    SET counted_quantity = ?, variance = ?, notes = ?
                    WHERE id = ?
                    """,
                    (counted_qty, variance, notes, item_id),
                )

    return True, "Sayım məlumatları yadda saxlanıldı."

def confirm_inventory_adjustments(current_user: dict, count_id: int, final_notes: str = "", ip_address: str = None) -> tuple[bool, str]:
    """
    Finalize inventory session:
    Applies physical counted quantities to the stock master and
    creates ledger adjustment records with variance details.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM inventory_counts WHERE id = ?", (count_id,))
        session = cursor.fetchone()
        if not session:
            return False, "Sayım sessiyası tapılmadı."
        if session["status"] != "draft":
            return False, "Bu sessiya artıq təsdiqlənmişdir."
        if current_user.get("role") != "developer" and session["branch_id"] != current_user.get("branch_id", 1):
            return False, "Bu inventarizasiya sizin filialınıza aid deyil."

        cursor.execute("SELECT * FROM inventory_count_items WHERE count_id = ?", (count_id,))
        items = cursor.fetchall()

        adjusted_count = 0
        for itm in items:
            mat_id = itm["raw_material_id"]
            counted = itm["counted_quantity"]
            variance = itm["variance"]

            if variance != 0:
                adjusted_count += 1
                cursor.execute("UPDATE raw_materials SET current_stock = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (counted, mat_id))

                note = f"İnventarizasiya #{count_id} düzəlişi: Fərq {variance:+.3f}"
                if itm["notes"]:
                    note += f" ({itm['notes']})"

                cursor.execute(
                    """
                    INSERT INTO stock_transactions
                    (branch_id, raw_material_id, change_amount, balance_after, reference_type, reference_id, notes, created_by)
                    VALUES (?, ?, ?, ?, 'inventory_adjustment', ?, ?, ?)
                    """,
                    (session["branch_id"], mat_id, variance, counted, count_id, note, current_user["id"]),
                )

        cursor.execute(
            """
            UPDATE inventory_counts
            SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP, notes = coalesce(nullif(?, ''), notes)
            WHERE id = ?
            """,
            (final_notes, count_id),
        )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="confirm_inventory_count",
        entity_type="inventory_counts",
        entity_id=count_id,
        details=f"İnventarizasiya təsdiqləndi: {adjusted_count} maddə üzrə qalıq yeniləndi",
        ip_address=ip_address,
    )

    return True, f"İnventarizasiya təsdiqləndi. {adjusted_count} xammal qalığı faktiki sayıma uyğunlaşdırıldı."

def list_inventory_sessions(branch_id: int = 1, limit: int = 20) -> list[dict]:
    """List historical inventory count sessions."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT c.*, u.full_name as auditor_name,
                   (SELECT count(*) FROM inventory_count_items WHERE count_id = c.id) as total_items,
                   (SELECT count(*) FROM inventory_count_items WHERE count_id = c.id AND variance != 0) as discrepancy_count
            FROM inventory_counts c
            JOIN users u ON c.user_id = u.id
            WHERE c.branch_id = ? OR c.branch_id IS NULL
            ORDER BY c.id DESC LIMIT ?
            """,
            (branch_id, limit),
        )
        return [dict_from_row(r) for r in cursor.fetchall()]
