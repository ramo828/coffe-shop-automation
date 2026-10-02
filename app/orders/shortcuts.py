"""
Barista Shortcuts Module
Allows baristas to customize their quick-access shortcuts panel,
pinning high-volume drinks for rapid one-touch entry.
"""
import logging
from app.core.database import get_db, dict_from_row

logger = logging.getLogger(__name__)

def get_user_shortcuts(user_id: int) -> list[dict]:
    """Retrieve pinned product variants for a barista with custom labels and icons."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT s.id as shortcut_id, s.sort_order, s.custom_label, s.icon_url,
                   v.id as variant_id, v.name as variant_name, v.price,
                   p.id as product_id, p.name as product_name, p.category, p.image_url
            FROM user_shortcuts s
            JOIN product_variants v ON s.variant_id = v.id
            JOIN products p ON v.product_id = p.id
            WHERE s.user_id = ? AND v.is_active = 1 AND p.is_active = 1
            ORDER BY s.sort_order ASC, p.name ASC
            """,
            (user_id,),
        )
        return [dict_from_row(r) for r in cursor.fetchall()]

def add_user_shortcut(user_id: int, variant_id: int, custom_label: str = None, icon_url: str = None) -> tuple[bool, str, dict | None]:
    """Add a product variant to the barista's shortcuts panel."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Verify variant exists and is active
        cursor.execute(
            """
            SELECT v.id, v.name as variant_name, p.name as product_name
            FROM product_variants v
            JOIN products p ON v.product_id = p.id
            WHERE v.id = ? AND v.is_active = 1 AND p.is_active = 1
            """,
            (variant_id,),
        )
        var_row = cursor.fetchone()
        if not var_row:
            return False, "Məhsul və ya növ tapılmadı.", None

        # Check if already present
        cursor.execute(
            "SELECT id FROM user_shortcuts WHERE user_id = ? AND variant_id = ?",
            (user_id, variant_id),
        )
        existing = cursor.fetchone()
        if existing:
            # Update existing shortcut
            shortcut_id = existing["id"]
            cursor.execute(
                """
                UPDATE user_shortcuts
                SET custom_label = COALESCE(?, custom_label),
                    icon_url = COALESCE(?, icon_url)
                WHERE id = ? AND user_id = ?
                """,
                (custom_label, icon_url, shortcut_id, user_id),
            )
            return True, "Qısayol yeniləndi.", {"shortcut_id": shortcut_id}

        # Determine next sort_order
        cursor.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 as next_order FROM user_shortcuts WHERE user_id = ?", (user_id,))
        next_order = cursor.fetchone()["next_order"]

        cursor.execute(
            """
            INSERT INTO user_shortcuts (user_id, variant_id, custom_label, icon_url, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, variant_id, custom_label, icon_url, next_order),
        )
        new_id = cursor.lastrowid
        return True, "Qısayol uğurla əlavə edildi.", {"shortcut_id": new_id}

def update_user_shortcut(user_id: int, shortcut_id: int, custom_label: str = None, icon_url: str = None) -> tuple[bool, str]:
    """Update custom label or icon of an existing shortcut."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM user_shortcuts WHERE id = ? AND user_id = ?",
            (shortcut_id, user_id),
        )
        if not cursor.fetchone():
            return False, "Qısayol tapılmadı."

        cursor.execute(
            """
            UPDATE user_shortcuts
            SET custom_label = ?, icon_url = ?
            WHERE id = ? AND user_id = ?
            """,
            (custom_label, icon_url, shortcut_id, user_id),
        )
        return True, "Qısayol yeniləndi."

def remove_user_shortcut(user_id: int, shortcut_id: int) -> tuple[bool, str]:
    """Remove a shortcut for a barista."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM user_shortcuts WHERE id = ? AND user_id = ?",
            (shortcut_id, user_id),
        )
        if cursor.rowcount == 0:
            return False, "Qısayol tapılmadı və ya artıq silinib."
        return True, "Qısayol silindi."

def reorder_user_shortcuts(user_id: int, shortcut_ids: list[int]) -> tuple[bool, str]:
    """Save the drag-and-drop ordering of shortcuts."""
    with get_db() as conn:
        cursor = conn.cursor()
        for idx, sid in enumerate(shortcut_ids):
            cursor.execute(
                "UPDATE user_shortcuts SET sort_order = ? WHERE id = ? AND user_id = ?",
                (idx, sid, user_id),
            )
        return True, "Qısayol ardıcıllığı saxlanıldı."

def set_user_shortcuts(user_id: int, variant_ids: list[int]) -> tuple[bool, str]:
    """Legacy helper: Save or update barista's pinned shortcuts list."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_shortcuts WHERE user_id = ?", (user_id,))
        for idx, var_id in enumerate(variant_ids):
            cursor.execute(
                """
                INSERT OR IGNORE INTO user_shortcuts (user_id, variant_id, sort_order)
                VALUES (?, ?, ?)
                """,
                (user_id, var_id, idx),
            )
    return True, "Qısayol paneli uğurla yeniləndi."

