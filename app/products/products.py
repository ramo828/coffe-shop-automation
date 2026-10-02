"""
Products and Variants Management Module
Handles coffee drinks, food, merchandise, and their sized/takeaway variants.
"""
import logging
import math
import sqlite3
from app.core.database import get_db, dict_from_row
from app.core.audit import log_business_action

logger = logging.getLogger(__name__)

def list_products(branch_id: int = 1, active_only: bool = False) -> list[dict]:
    """List all products with their nested variants."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM products WHERE (branch_id = ? OR branch_id IS NULL)"
        params = [branch_id]
        if active_only:
            query += " AND is_active = 1"
        query += " ORDER BY sort_order ASC, name ASC"

        cursor.execute(query, params)
        products = [dict_from_row(r) for r in cursor.fetchall()]

        # Fetch variants for each product
        for prod in products:
            var_query = "SELECT * FROM product_variants WHERE product_id = ?"
            if active_only:
                var_query += " AND is_active = 1"
            var_query += " ORDER BY price ASC, name ASC"
            cursor.execute(var_query, (prod["id"],))
            prod["variants"] = [dict_from_row(v) for v in cursor.fetchall()]

        return products


def reorder_products(product_ids: list[int], branch_id: int = 1) -> tuple[bool, str]:
    """Persist the POS display order for products in the current branch."""
    if not product_ids or len(set(product_ids)) != len(product_ids):
        return False, "Məhsul sırası düzgün deyil."
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in product_ids)
            cursor.execute(
                f"SELECT id FROM products WHERE id IN ({placeholders}) "
                "AND (branch_id = ? OR branch_id IS NULL)",
                (*product_ids, branch_id),
            )
            allowed = {int(row["id"]) for row in cursor.fetchall()}
            if allowed != set(product_ids):
                return False, "Məhsullardan biri bu filial üçün tapılmadı."
            cursor.executemany(
                "UPDATE products SET sort_order = ? WHERE id = ?",
                [(index, product_id) for index, product_id in enumerate(product_ids)],
            )
            return True, "Məhsul sırası yadda saxlanıldı."
    except sqlite3.Error:
        logger.exception("Failed to reorder products")
        return False, "Məhsul sırası yadda saxlanılmadı."

def get_product_by_id(product_id: int) -> dict | None:
    """Fetch single product with variants and recipes."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        prod = cursor.fetchone()
        if not prod:
            return None
        res = dict_from_row(prod)
        cursor.execute("SELECT * FROM product_variants WHERE product_id = ?", (product_id,))
        res["variants"] = [dict_from_row(v) for v in cursor.fetchall()]
        return res

def create_product(current_user: dict, data: dict, ip_address: str = None) -> tuple[dict | None, str]:
    """Create a new product with optional initial variants."""
    name = str(data.get("name", "")).strip()
    category = str(data.get("category", "Qəhvə")).strip()
    description = str(data.get("description", "")).strip()
    image_url = data.get("image_url", "/static/images/icons/premium-coffee.svg")
    sort_order = int(data.get("sort_order", 0))
    branch_id = current_user.get("branch_id", 1)

    if not name:
        return None, "Məhsulun adı mütləq qeyd edilməlidir."

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO products (branch_id, name, category, description, image_url, sort_order, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (branch_id, name, category, description, image_url, sort_order),
        )
        product_id = cursor.lastrowid

        # Insert initial variants if provided
        variants_data = data.get("variants", [])
        if not variants_data:
            # Default single standard variant if none given
            default_price = float(data.get("price", 0.0))
            cursor.execute(
                """
                INSERT INTO product_variants (product_id, name, price, sku, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (product_id, "Standart", default_price, f"SKU-{product_id}-STD"),
            )
        else:
            for v in variants_data:
                v_name = v.get("name", "Standart")
                v_price = float(v.get("price", 0.0))
                v_sku = v.get("sku", f"SKU-{product_id}-{v_name[:3].upper()}")
                cursor.execute(
                    """
                    INSERT INTO product_variants (product_id, name, price, sku, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (product_id, v_name, v_price, v_sku),
                )

        # Newly created drinks must be immediately available in every POS
        # user's quick-sale shortcuts, while INSERT OR IGNORE preserves
        # existing personal shortcut choices.
        cursor.execute(
            """
            INSERT OR IGNORE INTO user_shortcuts (user_id, variant_id, sort_order)
            SELECT u.id, v.id, COALESCE(
                (SELECT MAX(s.sort_order) + 1 FROM user_shortcuts s WHERE s.user_id = u.id), 0
            )
            FROM users u
            JOIN product_variants v ON v.product_id = ?
            WHERE u.is_active = 1
              AND u.role IN ('admin', 'developer', 'barista')
              AND (u.branch_id = ? OR u.branch_id IS NULL)
            """,
            (product_id, branch_id),
        )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="create_product",
        entity_type="products",
        entity_id=product_id,
        details=f"Yeni məhsul yaradıldı: {name}",
        ip_address=ip_address,
    )

    return get_product_by_id(product_id), "Məhsul uğurla əlavə edildi."

def update_product(current_user: dict, product_id: int, data: dict, ip_address: str = None) -> tuple[bool, str]:
    """Update product general details."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        prod = cursor.fetchone()
        if not prod:
            return False, "Məhsul tapılmadı."

        name = data.get("name", prod["name"])
        category = data.get("category", prod["category"])
        description = data.get("description", prod["description"])
        image_url = data.get("image_url", prod["image_url"])
        sort_order = data.get("sort_order", prod["sort_order"])
        is_active = data.get("is_active", prod["is_active"])

        cursor.execute(
            """
            UPDATE products
            SET name = ?, category = ?, description = ?, image_url = ?, sort_order = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, category, description, image_url, sort_order, is_active, product_id),
        )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="update_product",
        entity_type="products",
        entity_id=product_id,
        details=f"Məhsul yeniləndi: {name}",
        ip_address=ip_address,
    )
    return True, "Məhsul yeniləndi."

def delete_product(current_user: dict, product_id: int, hard_delete: bool = True, ip_address: str = None) -> tuple[bool, str]:
    """Delete a product. By default completely deletes product, variants, and recipes."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM products WHERE id = ?", (product_id,))
        prod = cursor.fetchone()
        if not prod:
            return False, "Məhsul tapılmadı."
        prod_name = prod["name"]

        if hard_delete:
            cursor.execute(
                """
                DELETE FROM recipes WHERE variant_id IN (
                    SELECT id FROM product_variants WHERE product_id = ?
                )
                """,
                (product_id,),
            )
            cursor.execute("DELETE FROM user_shortcuts WHERE variant_id IN (SELECT id FROM product_variants WHERE product_id = ?)", (product_id,))
            cursor.execute("DELETE FROM product_variants WHERE product_id = ?", (product_id,))
            cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        else:
            cursor.execute("UPDATE products SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (product_id,))

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="delete_product",
        entity_type="products",
        entity_id=product_id,
        details=f"Məhsul silindi: {prod_name}",
        ip_address=ip_address,
    )
    return True, f"'{prod_name}' məhsulu silindi."

def delete_product_variant(current_user: dict, variant_id: int, ip_address: str = None) -> tuple[bool, str]:
    """Delete a single product variant and its recipes."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, product_id FROM product_variants WHERE id = ?", (variant_id,))
        var = cursor.fetchone()
        if not var:
            return False, "Variant tapılmadı."
        var_name = var["name"]

        cursor.execute("DELETE FROM recipes WHERE variant_id = ?", (variant_id,))
        cursor.execute("DELETE FROM user_shortcuts WHERE variant_id = ?", (variant_id,))
        cursor.execute("DELETE FROM product_variants WHERE id = ?", (variant_id,))

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="delete_product_variant",
        entity_type="product_variants",
        entity_id=variant_id,
        details=f"Variant silindi: {var_name}",
        ip_address=ip_address,
    )
    return True, f"'{var_name}' variantı silindi."

def add_product_variant(current_user: dict, product_id: int, data: dict) -> tuple[dict | None, str]:
    """Add a new variant (e.g. Small, Large, Cup) to an existing product."""
    name = str(data.get("name", "")).strip()
    try:
        price = float(data.get("price", 0.0))
    except (TypeError, ValueError):
        return None, "Variant qiyməti düzgün rəqəm olmalıdır."
    sku = str(data.get("sku", "")).strip() or f"SKU-{product_id}-{name[:3].upper()}"

    if not name:
        return None, "Variant adı mütləq daxil edilməlidir."
    if not math.isfinite(price) or price <= 0:
        return None, "Variant qiyməti sıfırdan böyük olmalıdır."

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM products WHERE id = ?", (product_id,))
        if not cursor.fetchone():
            return None, "Məhsul tapılmadı."
        cursor.execute(
            "SELECT id FROM product_variants WHERE product_id = ? AND lower(name) = lower(?)",
            (product_id, name),
        )
        if cursor.fetchone():
            return None, "Bu məhsulda həmin variant artıq mövcuddur."
        try:
            cursor.execute(
                """
                INSERT INTO product_variants (product_id, name, price, sku, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (product_id, name, price, sku),
            )
        except sqlite3.IntegrityError:
            return None, "Variant əlavə edilə bilmədi: SKU artıq istifadə olunur."
        var_id = cursor.lastrowid
        cursor.execute(
            """
            INSERT OR IGNORE INTO user_shortcuts (user_id, variant_id, sort_order)
            SELECT u.id, ?, COALESCE(
                (SELECT MAX(s.sort_order) + 1 FROM user_shortcuts s WHERE s.user_id = u.id), 0
            )
            FROM users u
            JOIN products p ON p.id = ?
            WHERE u.is_active = 1
              AND u.role IN ('admin', 'developer', 'barista')
              AND (u.branch_id = p.branch_id OR p.branch_id IS NULL OR u.branch_id IS NULL)
            """,
            (var_id, product_id),
        )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="add_product_variant",
        entity_type="product_variants",
        entity_id=var_id,
        details=f"Variant əlavə edildi: {name} ({price:.2f} AZN)",
    )
    return {"id": var_id, "product_id": product_id, "name": name, "price": price, "sku": sku}, "Variant əlavə edildi."
