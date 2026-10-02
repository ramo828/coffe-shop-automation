"""
Raw Materials Module
Manages the coffee shop's primary stock truth: beans, milks, syrups, cups, lids, and consumables.
"""
import logging
from app.core.database import get_db, dict_from_row
from app.core.audit import log_business_action

logger = logging.getLogger(__name__)

def list_raw_materials(branch_id: int = 1, active_only: bool = True) -> list[dict]:
    """List all raw material items with current stock and alert indicators."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = """
            SELECT id, branch_id, name, category, unit, current_stock,
                   minimum_alert_threshold, cost_per_unit, is_active, updated_at,
                   (current_stock <= minimum_alert_threshold) as is_low_stock
            FROM raw_materials
            WHERE (branch_id = ? OR branch_id IS NULL)
        """
        params = [branch_id]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY category ASC, name ASC"

        cursor.execute(query, params)
        return [dict_from_row(r) for r in cursor.fetchall()]

def create_raw_material(current_user: dict, data: dict, ip_address: str = None) -> tuple[dict | None, str]:
    """Create a new raw material item."""
    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "Digər")).strip()
    unit = str(data.get("unit", "ədəd")).strip()
    initial_stock = float(data.get("initial_stock", 0.0))
    min_threshold = float(data.get("minimum_alert_threshold", 10.0))
    cost = float(data.get("cost_per_unit", 0.0))
    branch_id = current_user.get("branch_id", 1)

    if not name or not unit:
        return None, "Xammal adı və vahidi mütləq daxil edilməlidir."

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO raw_materials (branch_id, name, category, unit, current_stock, minimum_alert_threshold, cost_per_unit, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (branch_id, name, category, unit, initial_stock, min_threshold, cost),
        )
        mat_id = cursor.lastrowid

        if initial_stock > 0:
            cursor.execute(
                """
                INSERT INTO stock_transactions (branch_id, raw_material_id, change_amount, balance_after, reference_type, notes, created_by)
                VALUES (?, ?, ?, ?, 'restock', 'İlkin qalıq daxil edilməsi', ?)
                """,
                (branch_id, mat_id, initial_stock, initial_stock, current_user["id"]),
            )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="create_raw_material",
        entity_type="raw_materials",
        entity_id=mat_id,
        details=f"Yeni xammal əlavə edildi: {name} ({initial_stock} {unit})",
        ip_address=ip_address,
    )

    return {"id": mat_id, "name": name, "category": category, "unit": unit, "current_stock": initial_stock}, "Xammal uğurla əlavə edildi."

def restock_raw_material(current_user: dict, material_id: int, quantity: float, notes: str = "", ip_address: str = None, waste_quantity: float = 0.0) -> tuple[bool, str]:
    """Increase stock quantity for a raw material (receipt of goods)."""
    if quantity <= 0 or waste_quantity < 0:
        return False, "Mədaxil miqdarı sıfırdan böyük olmalıdır."

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM raw_materials WHERE id = ?", (material_id,))
        mat = cursor.fetchone()
        if not mat:
            return False, "Xammal tapılmadı."

        new_balance = round(mat["current_stock"] + quantity, 3)
        cursor.execute("UPDATE raw_materials SET current_stock = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_balance, material_id))

        cursor.execute(
            """
            INSERT INTO stock_transactions (branch_id, raw_material_id, change_amount, balance_after, reference_type, notes, created_by)
            VALUES (?, ?, ?, ?, 'restock', ?, ?)
            """,
            (mat["branch_id"], material_id, quantity, new_balance, notes or "Anbara mədaxil", current_user["id"]),
        )
        if waste_quantity:
            cursor.execute(
                """INSERT INTO stock_transactions
                   (branch_id, raw_material_id, change_amount, balance_after, reference_type, notes, created_by, waste_quantity)
                   VALUES (?, ?, 0, ?, 'spillage_waste', ?, ?, ?)""",
                (mat["branch_id"], material_id, new_balance, f"Qəbul itkisi: {waste_quantity} {mat['unit']}. {notes}".strip(), current_user["id"], waste_quantity),
            )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="restock_raw_material",
        entity_type="raw_materials",
        entity_id=material_id,
        details=f"Mədaxil: +{quantity} {mat['unit']}, itki: {waste_quantity} {mat['unit']} -> Yeni qalıq: {new_balance} {mat['unit']}",
        ip_address=ip_address,
    )

    return True, f"Anbar qalığı artırıldı (+{quantity} {mat['unit']}). Yeni qalıq: {new_balance} {mat['unit']}."

def update_raw_material(current_user: dict, material_id: int, data: dict, ip_address: str = None) -> tuple[dict | None, str]:
    """Edit raw material details and correct stock quantity."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM raw_materials WHERE id = ?", (material_id,))
        mat = cursor.fetchone()
        if not mat:
            return None, "Xammal tapılmadı."

        name = str(data.get("name", mat["name"])).strip()
        category = str(data.get("category", mat["category"])).strip()
        unit = str(data.get("unit", mat["unit"])).strip()
        new_stock = float(data.get("current_stock", mat["current_stock"]))
        min_threshold = float(data.get("minimum_alert_threshold", mat["minimum_alert_threshold"]))
        cost = float(data.get("cost_per_unit", mat["cost_per_unit"]))
        is_active = int(data.get("is_active", mat["is_active"]))

        stock_diff = round(new_stock - mat["current_stock"], 3)

        cursor.execute(
            """
            UPDATE raw_materials
            SET name = ?, category = ?, unit = ?, current_stock = ?, minimum_alert_threshold = ?, cost_per_unit = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, category, unit, new_stock, min_threshold, cost, is_active, material_id),
        )

        if stock_diff != 0:
            cursor.execute(
                """
                INSERT INTO stock_transactions (branch_id, raw_material_id, change_amount, balance_after, reference_type, notes, created_by)
                VALUES (?, ?, ?, ?, 'inventory_adjustment', 'Düzəliş redaktəsi', ?)
                """,
                (mat["branch_id"], material_id, stock_diff, new_stock, current_user["id"]),
            )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="update_raw_material",
        entity_type="raw_materials",
        entity_id=material_id,
        details=f"Xammal redaktə edildi: {name}, Yeni qalıq: {new_stock} {unit}",
        ip_address=ip_address,
    )

    return {"id": material_id, "name": name, "category": category, "unit": unit, "current_stock": new_stock}, "Xammal məlumatları yeniləndi."

def delete_raw_material(current_user: dict, material_id: int, ip_address: str = None) -> tuple[bool, str]:
    """Delete a raw material item and purge recipe references."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM raw_materials WHERE id = ?", (material_id,))
        mat = cursor.fetchone()
        if not mat:
            return False, "Xammal tapılmadı."

        # Remove recipe links
        cursor.execute("DELETE FROM recipes WHERE raw_material_id = ?", (material_id,))
        cursor.execute("DELETE FROM stock_transactions WHERE raw_material_id = ?", (material_id,))
        cursor.execute("DELETE FROM raw_materials WHERE id = ?", (material_id,))

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="delete_raw_material",
        entity_type="raw_materials",
        entity_id=material_id,
        details=f"Xammal silindi: {mat['name']}",
        ip_address=ip_address,
    )
    return True, f"'{mat['name']}' xammalı uğurla silindi."
