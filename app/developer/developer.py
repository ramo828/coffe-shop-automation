"""
Developer Technical Tools Module
Provides REAL-mode exports (.sql, .json, .txt tree format),
database encryption/compression controls, and system diagnostics.
"""
import os
import json
import psutil
import logging
from pathlib import Path
from app.core.config import DB_PATH, DEFAULT_BRANCH_CODE
from app.core.database import get_db, dict_from_row
from app.security.license import get_system_license_status
from app.core.audit import log_developer_action

logger = logging.getLogger(__name__)

def get_system_diagnostics() -> dict:
    """Retrieve technical health statistics for developer dashboard."""
    db_size_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    license_status = get_system_license_status()

    # System process info
    proc = psutil.Process(os.getpid())
    mem_info = proc.memory_info()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM orders")
        total_orders = cursor.fetchone()[0]

        cursor.execute("SELECT count(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT count(*) FROM raw_materials")
        total_materials = cursor.fetchone()[0]

        cursor.execute("SELECT key, value FROM system_settings WHERE key IN ('encryption_enabled', 'compression_enabled', 'shop_name', 'accent_color')")
        settings = {row[0]: row[1] for row in cursor.fetchall()}

    return {
        "system_status": "healthy",
        "database_file": str(DB_PATH),
        "database_size_kb": round(db_size_bytes / 1024, 2),
        "memory_usage_mb": round(mem_info.rss / (1024 * 1024), 2),
        "cpu_percent": proc.cpu_percent(interval=None),
        "license": license_status,
        "counts": {
            "orders": total_orders,
            "users": total_users,
            "raw_materials": total_materials,
        },
        "features": {
            "encryption_enabled": settings.get("encryption_enabled") == "1",
            "compression_enabled": settings.get("compression_enabled") == "1",
            "shop_name": settings.get("shop_name", "Illy Specialty Coffee"),
            "accent_color": settings.get("accent_color", "#c8102e"),
        }
    }

def update_system_branding(data: dict) -> tuple[bool, str]:
    """Update shop branding, theme accent, or company title."""
    with get_db() as conn:
        for k in ["shop_name", "shop_tagline", "accent_color", "logo_url", "banner_url"]:
            if k in data:
                conn.execute(
                    "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (k, str(data[k])),
                )
    log_developer_action("update_branding", details="Sistem brendinq parametrləri yeniləndi")
    return True, "Brendinq parametrləri yeniləndi."

def set_encryption_mode(enabled: bool, passphrase: str = "") -> tuple[bool, str]:
    """Toggle database encrypted mode status."""
    val = "1" if enabled else "0"
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('encryption_enabled', ?, CURRENT_TIMESTAMP)", (val,))
    log_developer_action("toggle_encryption", details=f"Şifrələmə rejimi: {'Aktiv' if enabled else 'Deaktiv'}")
    return True, f"Şifrələmə rejimi {'aktivləşdirildi' if enabled else 'deaktivləşdirildi'}."

def set_compression_mode(enabled: bool) -> tuple[bool, str]:
    """Toggle database GZ compression mode status."""
    val = "1" if enabled else "0"
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('compression_enabled', ?, CURRENT_TIMESTAMP)", (val,))
    log_developer_action("toggle_compression", details=f"GZ sıxılma rejimi: {'Aktiv' if enabled else 'Deaktiv'}")
    return True, f"GZ sıxılma rejimi {'aktivləşdirildi' if enabled else 'deaktivləşdirildi'}."


def list_developer_audit_logs(limit: int = 50) -> list[dict]:
    """Retrieve technical developer audit trail."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM developer_audit_logs ORDER BY id DESC LIMIT ?", (limit,))
        return [dict_from_row(r) for r in cursor.fetchall()]

# --- REAL-Mode Database Export Tools (Section M5) ---

def export_db_sql() -> tuple[str | None, str]:
    """Export full database as standard SQL script. (REAL mode only)"""
    license_status = get_system_license_status()
    if not license_status.get("is_real_mode"):
        return None, "Baza ixracı yalnız REAL rejim aktiv olduqda mümkündür."

    with get_db() as conn:
        lines = []
        for line in conn.iterdump():
            lines.append(line)
        sql_dump = "\n".join(lines)

    log_developer_action("export_db_sql", details="Baza .sql formatında ixrac edildi")
    return sql_dump, "SQL ixracı hazırdır."

def export_db_json() -> tuple[str | None, str]:
    """Export full database in hierarchical JSON format. (REAL mode only)"""
    license_status = get_system_license_status()
    if not license_status.get("is_real_mode"):
        return None, "Baza ixracı yalnız REAL rejim aktiv olduqda mümkündür."

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, code, address FROM branches")
        branches = [dict_from_row(r) for r in cursor.fetchall()]

        cursor.execute("SELECT id, username, full_name, role, avatar_url, is_active FROM users WHERE role != 'developer'")
        users = [dict_from_row(r) for r in cursor.fetchall()]

        cursor.execute("SELECT id, name, category, unit, current_stock, minimum_alert_threshold, cost_per_unit FROM raw_materials")
        materials = [dict_from_row(r) for r in cursor.fetchall()]

        cursor.execute("SELECT * FROM products")
        products = [dict_from_row(r) for r in cursor.fetchall()]

        for p in products:
            cursor.execute("SELECT * FROM product_variants WHERE product_id = ?", (p["id"],))
            p["variants"] = [dict_from_row(v) for v in cursor.fetchall()]
            for v in p["variants"]:
                cursor.execute(
                    """
                    SELECT r.quantity, m.name as material_name, m.unit as material_unit
                    FROM recipes r JOIN raw_materials m ON r.raw_material_id = m.id
                    WHERE r.variant_id = ?
                    """,
                    (v["id"],),
                )
                v["recipe"] = [dict_from_row(rec) for rec in cursor.fetchall()]

        cursor.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 100")
        orders = [dict_from_row(r) for r in cursor.fetchall()]
        for o in orders:
            cursor.execute("SELECT * FROM order_items WHERE order_id = ?", (o["id"],))
            o["items"] = [dict_from_row(i) for i in cursor.fetchall()]

        payload = {
            "system": "Illy Specialty Coffee Management System",
            "version": "1.0.0-production",
            "exported_at": psutil.datetime.datetime.now().isoformat(),
            "branches": branches,
            "staff_users": users,
            "raw_materials": materials,
            "menu_catalog": products,
            "recent_orders": orders,
        }

    log_developer_action("export_db_json", details="Baza .json formatında ixrac edildi")
    return json.dumps(payload, indent=2, ensure_ascii=False), "JSON ixracı hazırdır."

def export_db_tree_txt() -> tuple[str | None, str]:
    """Export structured tree view in human-readable text format. (REAL mode only)"""
    license_status = get_system_license_status()
    if not license_status.get("is_real_mode"):
        return None, "Baza ixracı yalnız REAL rejim aktiv olduqda mümkündür."

    with get_db() as conn:
        cursor = conn.cursor()

        lines = [
            "============================================================",
            "  ILLY SPECIALTY COFFEE - STRUKTUR VƏ MƏLUMAT AĞACI (TREE)  ",
            "============================================================",
            f"İxrac tarixi: {psutil.datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "Rejim: REAL Lisenziyalı Rejim",
            "",
            "├── [Filiallar]",
        ]

        cursor.execute("SELECT id, name, code FROM branches")
        for b in cursor.fetchall():
            lines.append(f"│   └── #{b['id']} {b['name']} ({b['code']})")

        lines.append("├── [İşçi Heyəti]")
        cursor.execute("SELECT id, full_name, username, role FROM users WHERE role != 'developer'")
        for u in cursor.fetchall():
            lines.append(f"│   └── [{u['role'].upper()}] {u['full_name']} (@{u['username']})")

        lines.append("├── [Anbar və Xammal Qalıqları]")
        cursor.execute("SELECT id, name, category, current_stock, unit FROM raw_materials ORDER BY category")
        for m in cursor.fetchall():
            lines.append(f"│   └── {m['name']} ({m['category']}): {m['current_stock']} {m['unit']}")

        lines.append("├── [Menyu və Reseptlər]")
        cursor.execute("SELECT id, name, category FROM products ORDER BY category, name")
        for p in cursor.fetchall():
            lines.append(f"│   ├── {p['name']} [{p['category']}]")
            cursor.execute("SELECT id, name, price FROM product_variants WHERE product_id = ?", (p["id"],))
            variants = cursor.fetchall()
            for v in variants:
                lines.append(f"│   │   └── Variant: {v['name']} - {v['price']:.2f} AZN")
                cursor.execute(
                    """
                    SELECT m.name, r.quantity, m.unit
                    FROM recipes r JOIN raw_materials m ON r.raw_material_id = m.id
                    WHERE r.variant_id = ?
                    """,
                    (v["id"],),
                )
                for r in cursor.fetchall():
                    lines.append(f"│   │       ├── Resept: {r['quantity']} {r['unit']} {r['name']}")

        lines.append("└── [Əməliyyat Xülasəsi]")
        cursor.execute("SELECT count(*) as total, sum(final_amount) as rev FROM orders WHERE status = 'completed'")
        ord_sum = cursor.fetchone()
        lines.append(f"    ├── Ümumi tamamlanmış satışlar: {ord_sum['total'] or 0} ədəd")
        lines.append(f"    └── Ümumi dövriyyə: {ord_sum['rev'] or 0.0:.2f} AZN")
        lines.append("============================================================")

    log_developer_action("export_db_txt", details="Baza .txt ağac formatında ixrac edildi")
    return "\n".join(lines), "TXT ağac ixracı hazırdır."
