"""
Audit Logging Module
Guarantees traceability of all operational actions by Admin and Barista,
as well as technical operations performed by Developer.
"""
import json
import logging
from app.core.database import get_db

logger = logging.getLogger(__name__)

def log_business_action(user_id, username, role, action, entity_type=None, entity_id=None, details=None, branch_id=1, ip_address=None):
    """Log an operational action performed by Admin or Barista."""
    details_str = json.dumps(details, ensure_ascii=False) if isinstance(details, (dict, list)) else str(details or "")
    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (branch_id, user_id, username, role, action, entity_type, entity_id, details, ip_address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (branch_id, user_id, username, role, action, entity_type, entity_id, details_str, ip_address),
            )
    except Exception as e:
        logger.error(f"Failed to record audit log: {e}")

def log_developer_action(action, details=None, ip_address=None):
    """Log a deep technical operation performed by Developer."""
    details_str = json.dumps(details, ensure_ascii=False) if isinstance(details, (dict, list)) else str(details or "")
    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO developer_audit_logs (action, details, ip_address)
                VALUES (?, ?, ?)
                """,
                (action, details_str, ip_address),
            )
    except Exception as e:
        logger.error(f"Failed to record developer audit log: {e}")
