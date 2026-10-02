"""
Flexible Recipes Module
Links product variants to an arbitrary number of raw materials (beans, milk, cups, lids, syrups).
"""
import logging
from app.core.database import get_db, dict_from_row
from app.core.audit import log_business_action

logger = logging.getLogger(__name__)

def get_recipe_for_variant(variant_id: int) -> list[dict]:
    """Retrieve full ingredient recipe for a product variant."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT r.id, r.variant_id, r.raw_material_id, r.quantity,
                   m.name as material_name, m.unit as material_unit,
                   m.current_stock, m.cost_per_unit,
                   r.waste_factor,
                   (r.quantity * r.waste_factor * m.cost_per_unit) as ingredient_cost,
                   pv.price,
                   CASE WHEN pv.price > 0 THEN ((r.quantity * r.waste_factor * m.cost_per_unit) / pv.price) * 100 ELSE 0 END as food_cost_percent
            FROM recipes r
            JOIN raw_materials m ON r.raw_material_id = m.id
            JOIN product_variants pv ON pv.id = r.variant_id
            WHERE r.variant_id = ?
            ORDER BY m.category ASC, m.name ASC
            """,
            (variant_id,),
        )
        return [dict_from_row(r) for r in cursor.fetchall()]

def set_recipe_for_variant(current_user: dict, variant_id: int, ingredients: list[dict], ip_address: str = None) -> tuple[bool, str]:
    """
    Set or update the entire recipe for a product variant.
    ingredients: [{"raw_material_id": int, "quantity": float, "waste_factor": float}, ...]
    """
    if not isinstance(ingredients, list):
        return False, "Resept maddələri siyahı şəklində olmalıdır."

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM product_variants WHERE id = ?", (variant_id,))
        var = cursor.fetchone()
        if not var:
            return False, "Məhsul variantı tapılmadı."

        # Clear existing recipe for this variant
        cursor.execute("DELETE FROM recipes WHERE variant_id = ?", (variant_id,))

        # Insert new ingredients
        for item in ingredients:
            mat_id = item.get("raw_material_id")
            qty = float(item.get("quantity", 0.0))
            waste_factor = float(item.get("waste_factor", 1.0))
            if waste_factor < 1.0:
                return False, "İtki faktoru 1.0 və ya daha böyük olmalıdır."
            if mat_id and qty > 0:
                cursor.execute(
                    """
                    INSERT INTO recipes (variant_id, raw_material_id, quantity, waste_factor)
                    VALUES (?, ?, ?, ?)
                    """,
                    (variant_id, mat_id, qty, waste_factor),
                )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="set_recipe",
        entity_type="product_variants",
        entity_id=variant_id,
        details=f"Variant üçün resept yeniləndi: {var['name']} ({len(ingredients)} tərkib hissəsi)",
        ip_address=ip_address,
    )

    return True, f"'{var['name']}' üçün resept uğurla saxlanıldı."

def delete_recipe_ingredient(current_user: dict, recipe_id: int, ip_address: str = None) -> tuple[bool, str]:
    """Delete a single ingredient row from a recipe."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT variant_id FROM recipes WHERE id = ?", (recipe_id,))
        row = cursor.fetchone()
        if not row:
            return False, "Resept sətri tapılmadı."
        cursor.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="delete_recipe_ingredient",
        entity_type="recipes",
        entity_id=recipe_id,
        details=f"Resept tərkib hissəsi silindi: ID {recipe_id}",
        ip_address=ip_address,
    )
    return True, "Reseptdən tərkib hissəsi silindi."

def clear_variant_recipe(current_user: dict, variant_id: int, ip_address: str = None) -> tuple[bool, str]:
    """Clear all ingredients from a product variant's recipe."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM recipes WHERE variant_id = ?", (variant_id,))

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="clear_recipe",
        entity_type="product_variants",
        entity_id=variant_id,
        details=f"Variant üçün resept tam təmizləndi: Variant {variant_id}",
        ip_address=ip_address,
    )
    return True, "Resept tam təmizləndi."
