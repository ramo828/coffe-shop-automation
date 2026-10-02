"""Stock and operational alerts."""
from datetime import datetime, timezone

from app.core.database import get_db, dict_from_row


def refresh_low_stock_alerts(branch_id=None):
    """Create/update low-stock alerts and return active alerts."""
    with get_db() as conn:
        query = """SELECT id, branch_id, name, current_stock, minimum_alert_threshold
                   FROM raw_materials
                   WHERE is_active = 1 AND current_stock <= minimum_alert_threshold"""
        params = ()
        if branch_id is not None:
            query += " AND (branch_id = ? OR branch_id IS NULL)"
            params = (branch_id,)
        materials = conn.execute(query, params).fetchall()
        for material in materials:
            existing = conn.execute(
                "SELECT id FROM alerts WHERE type = 'low_stock' AND entity_id = ? AND resolved_at IS NULL",
                (material["id"],),
            ).fetchone()
            message = f"{material['name']} stock is low ({material['current_stock']} <= {material['minimum_alert_threshold']})"
            if existing:
                conn.execute("UPDATE alerts SET message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                             (message, existing["id"]))
            else:
                conn.execute(
                    """INSERT INTO alerts (branch_id, type, severity, message, entity_id, created_at, updated_at)
                       VALUES (?, 'low_stock', 'warning', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                    (material["branch_id"], message, material["id"]),
                )
        return list_alerts(branch_id=branch_id, conn=conn)


def list_alerts(branch_id=None, include_resolved=False, limit=100, conn=None):
    own = conn is None
    if own:
        context = get_db()
        conn = context.__enter__()
    try:
        query = """SELECT a.*, rm.name AS entity_name
                   FROM alerts a
                   LEFT JOIN raw_materials rm ON a.type = 'low_stock' AND rm.id = a.entity_id
                   WHERE 1=1"""
        params = []
        if not include_resolved:
            query += " AND a.resolved_at IS NULL"
        if branch_id is not None:
            query += " AND (a.branch_id = ? OR a.branch_id IS NULL)"
            params.append(branch_id)
        query += " ORDER BY CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, a.created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        return [dict_from_row(row) for row in conn.execute(query, params).fetchall()]
    finally:
        if own:
            context.__exit__(None, None, None)


def acknowledge_alert(alert_id, user_id=None, branch_id=None):
    with get_db() as conn:
        branch_filter = "" if branch_id is None else " AND (branch_id = ? OR branch_id IS NULL)"
        params = [user_id, alert_id] + ([] if branch_id is None else [branch_id])
        result = conn.execute(
            "UPDATE alerts SET resolved_at = CURRENT_TIMESTAMP, resolved_by = ?, updated_at = CURRENT_TIMESTAMP "
            f"WHERE id = ? AND resolved_at IS NULL{branch_filter}", params)
        return result.rowcount > 0


def get_alert_summary(branch_id=None):
    alerts = refresh_low_stock_alerts(branch_id)
    return {"alerts": alerts, "count": len(alerts), "generated_at": datetime.now(timezone.utc).isoformat()}
