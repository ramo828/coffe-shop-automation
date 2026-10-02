"""
Stock Engine Module
Handles atomic stock deductions on order confirmation and
accurate stock reversals upon order void/cancellation.
"""
import logging
from app.core.database import get_db, dict_from_row

logger = logging.getLogger(__name__)

class InsufficientStockError(ValueError):
    """Raised when an order would make one or more materials negative."""

def deduct_stock_for_order(conn, order_id: int, user_id: int, branch_id: int = 1):
    """
    Deduct raw materials atomically for all items in an order based on recipes.
    Executes within an existing database transaction (conn).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT variant_id, quantity, product_name, variant_name FROM order_items WHERE order_id = ?", (order_id,))
    items = cursor.fetchall()

    required = {}
    for item in items:
        variant_id = item["variant_id"]
        ordered_qty = item["quantity"]

        if not variant_id:
            continue

        # Fetch recipe for this variant
        cursor.execute("SELECT raw_material_id, quantity, waste_factor FROM recipes WHERE variant_id = ?", (variant_id,))
        ingredients = cursor.fetchall()

        for ing in ingredients:
            mat_id = ing["raw_material_id"]
            total_deduction = round(ing["quantity"] * ing["waste_factor"] * ordered_qty, 3)
            required[mat_id] = required.get(mat_id, 0) + total_deduction

    for mat_id, total_deduction in required.items():
            cursor.execute(
                """SELECT current_stock, unit, name FROM raw_materials
                   WHERE id = ? AND (branch_id = ? OR branch_id IS NULL)""",
                (mat_id, branch_id),
            )
            mat = cursor.fetchone()
            if not mat:
                raise InsufficientStockError("Reseptdə göstərilən xammal tapılmadı.")
            if float(mat["current_stock"]) < total_deduction:
                raise InsufficientStockError(
                    f"'{mat['name']}' üçün kifayət qədər qalıq yoxdur: "
                    f"{mat['current_stock']} {mat['unit']} mövcuddur, {total_deduction} {mat['unit']} tələb olunur."
                )

            new_balance = round(mat["current_stock"] - total_deduction, 3)

            # Update raw material stock
            cursor.execute(
                """UPDATE raw_materials SET current_stock = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND (branch_id = ? OR branch_id IS NULL) AND current_stock >= ?""",
                (new_balance, mat_id, branch_id, total_deduction),
            )
            if cursor.rowcount != 1:
                raise InsufficientStockError(f"'{mat['name']}' qalıq əməliyyat zamanı dəyişdi. Sifariş yenidən yoxlanmalıdır.")

            # Log stock transaction
            cursor.execute(
                """
                INSERT INTO stock_transactions
                (branch_id, raw_material_id, change_amount, balance_after, reference_type, reference_id, notes, created_by)
                VALUES (?, ?, ?, ?, 'order', ?, ?, ?)
                """,
                (
                    branch_id,
                    mat_id,
                    -total_deduction,
                    new_balance,
                    order_id,
                    f"Sifariş #{order_id}: resept üzrə xammal silinməsi",
                    user_id,
                ),
            )

def reverse_stock_for_order(conn, order_id: int, user_id: int, branch_id: int = 1, reason: str = ""):
    """
    Reverse raw material deductions for a cancelled/voided order.
    Executes within an existing database transaction (conn).
    """
    cursor = conn.cursor()

    # Find all stock transactions created by this order
    cursor.execute(
        """
        SELECT raw_material_id, change_amount
        FROM stock_transactions
        WHERE reference_type = 'order' AND reference_id = ?
        """,
        (order_id,),
    )
    txs = cursor.fetchall()

    for tx in txs:
        mat_id = tx["raw_material_id"]
        # change_amount was negative, so to reverse we add the absolute value
        restore_amount = abs(tx["change_amount"])

        cursor.execute(
            """SELECT current_stock, unit, name FROM raw_materials
               WHERE id = ? AND (branch_id = ? OR branch_id IS NULL)""",
            (mat_id, branch_id),
        )
        mat = cursor.fetchone()
        if not mat:
            continue

        new_balance = round(mat["current_stock"] + restore_amount, 3)

        cursor.execute(
            """UPDATE raw_materials SET current_stock = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND (branch_id = ? OR branch_id IS NULL)""",
            (new_balance, mat_id, branch_id),
        )

        cursor.execute(
            """
            INSERT INTO stock_transactions
            (branch_id, raw_material_id, change_amount, balance_after, reference_type, reference_id, notes, created_by)
            VALUES (?, ?, ?, ?, 'order_cancel', ?, ?, ?)
            """,
            (
                branch_id,
                mat_id,
                restore_amount,
                new_balance,
                order_id,
                f"Sifariş #{order_id} ləğv edildi: Anbar bərpa olundu ({reason or 'Səbəb göstərilməyib'})",
                user_id,
            ),
        )
