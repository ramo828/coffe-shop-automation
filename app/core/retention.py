"""
Data Retention Policy Module
Safely purges historical operational transactions according to configured retention periods
while strictly guaranteeing preservation of ML models, user accounts, stock masters, and recipes.
"""
import logging
from app.core.database import get_db
from app.core.audit import log_developer_action

logger = logging.getLogger(__name__)

RETENTION_DAYS_MAP = {
    "1_week": 7,
    "1_month": 30,
    "1_year": 365,
    "never": None,
}

def get_current_retention_policy() -> str:
    """Retrieve current configured retention policy."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM system_settings WHERE key = 'retention_policy'")
        row = cursor.fetchone()
        return row[0] if row else "never"

def set_retention_policy(policy: str) -> tuple[bool, str]:
    """Update configured retention policy."""
    if policy not in RETENTION_DAYS_MAP:
        return False, "Yalnış saxlama siyasəti seçimi."

    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('retention_policy', ?, CURRENT_TIMESTAMP)",
            (policy,),
        )
    return True, f"Məlumatların saxlanma müddəti yeniləndi: {policy}"

def execute_retention_cleanup() -> dict:
    """
    Execute data retention cleanup strictly conforming to Section M3:
    STRICT IMMUNITY LIST:
      - ml_models (ML weights & learned models)
      - users (account information & credentials)
      - raw_materials (stock master truth)
      - products & product_variants
      - recipes (flexible recipes)
      - system_settings & branches
    """
    policy = get_current_retention_policy()
    days = RETENTION_DAYS_MAP.get(policy)

    if not days:
        return {
            "policy": policy,
            "purged": False,
            "message": "Siyasət 'Həmişə saxla' (Never) olaraq təyin edilib. Heç bir məlumat silinmədi.",
        }

    cutoff_clause = f"-{days} days"
    purged_counts = {"orders": 0, "audit_logs": 0, "shifts": 0}

    with get_db() as conn:
        cursor = conn.cursor()

        # Count and delete old orders
        cursor.execute(
            "SELECT count(*) FROM orders WHERE created_at < datetime('now', ?)",
            (cutoff_clause,),
        )
        purged_counts["orders"] = cursor.fetchone()[0]
        cursor.execute("DELETE FROM orders WHERE created_at < datetime('now', ?)", (cutoff_clause,))

        # Count and delete old general audit logs
        cursor.execute(
            "SELECT count(*) FROM audit_logs WHERE created_at < datetime('now', ?)",
            (cutoff_clause,),
        )
        purged_counts["audit_logs"] = cursor.fetchone()[0]
        cursor.execute("DELETE FROM audit_logs WHERE created_at < datetime('now', ?)", (cutoff_clause,))

        # Delete closed shifts older than cutoff
        cursor.execute(
            "SELECT count(*) FROM shifts WHERE status = 'closed' AND created_at < datetime('now', ?)",
            (cutoff_clause,),
        )
        purged_counts["shifts"] = cursor.fetchone()[0]
        cursor.execute(
            """
            DELETE FROM shifts
            WHERE status = 'closed'
              AND created_at < datetime('now', ?)
              AND NOT EXISTS (
                  SELECT 1 FROM orders
                  WHERE orders.shift_id = shifts.id
              )
            """,
            (cutoff_clause,),
        )

    log_developer_action(
        action="retention_cleanup",
        details=f"Retention policy ({policy}): Silindi {purged_counts['orders']} köhnə sifariş, {purged_counts['shifts']} növbə, {purged_counts['audit_logs']} audit jurnalı.",
    )

    return {
        "policy": policy,
        "purged": True,
        "purged_counts": purged_counts,
        "message": f"Köhnə əməliyyat məlumatları təmizləndi ({policy} siyasəti üzrə). ML modelləri və xammal qalıqları qorundu.",
    }
