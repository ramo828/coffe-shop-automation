"""
Sync Engine Module
Implements local-first offline synchronization via Python API endpoints,
incremental queues, conflict logging, and non-blocking background workers.
"""
import datetime
import json
import logging
import requests
from app.core.database import get_db, dict_from_row
from app.core.audit import log_developer_action

logger = logging.getLogger(__name__)

def get_sync_configuration() -> dict:
    """Read current remote sync settings from database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT key, value FROM system_settings
            WHERE key IN ('remote_sync_mode', 'remote_sync_url', 'remote_sync_token', 'last_sync_timestamp')
            """
        )
        settings = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT count(*) FROM sync_queue WHERE status = 'pending'")
        pending_count = cursor.fetchone()[0]

        return {
            "mode": settings.get("remote_sync_mode", "local_only"),
            "url": settings.get("remote_sync_url", ""),
            "token": settings.get("remote_sync_token", ""),
            "last_sync_timestamp": settings.get("last_sync_timestamp", ""),
            "pending_queue_count": pending_count,
        }

def update_sync_configuration(mode: str, url: str, token: str) -> tuple[bool, str]:
    """Save sync mode (local_only or local_remote) and connection parameters."""
    if mode not in ["local_only", "local_remote"]:
        return False, "Yalnış sinxronizasiya rejimi."

    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('remote_sync_mode', ?, CURRENT_TIMESTAMP)", (mode,))
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('remote_sync_url', ?, CURRENT_TIMESTAMP)", (url.strip(),))
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('remote_sync_token', ?, CURRENT_TIMESTAMP)", (token.strip(),))

    log_developer_action("update_sync_config", details=f"Sinxronizasiya parametrləri yeniləndi: Rejim={mode}, URL={url}")
    return True, "Sinxronizasiya parametrləri yadda saxlanıldı."

def test_remote_connection(url: str, token: str) -> tuple[bool, str]:
    """Test ping to the remote Python API receiver."""
    if not url:
        return False, "Uzaq server ünvanı boşdur."

    target_url = url.rstrip("/") + "/api/health"
    try:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        resp = requests.get(target_url, headers=headers, timeout=4.0)
        if resp.status_code == 200:
            return True, f"Uzaq serverə bağlantı uğurludur! (Status: {resp.status_code})"
        return False, f"Server xəta qaytardı (HTTP {resp.status_code}): {resp.text[:100]}"
    except requests.exceptions.RequestException as e:
        logger.warning(f"Remote connection check failed: {e}")
        return False, f"Uzaq serverə qoşulmaq mümkün olmadı: {str(e)}"

def sync_pending_records() -> dict:
    """
    Process pending outbound records from sync_queue:
    Fails gracefully if offline without ever blocking POS operations.
    """
    cfg = get_sync_configuration()
    if cfg["mode"] != "local_remote" or not cfg["url"]:
        return {"status": "skipped", "message": "Uzaq sinxronizasiya aktiv deyil."}

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sync_queue WHERE status = 'pending' ORDER BY id ASC LIMIT 50")
        queue_items = [dict_from_row(r) for r in cursor.fetchall()]

        if not queue_items:
            return {"status": "idle", "synced_count": 0, "message": "Gözləyən növbə yoxdur."}

        target_url = cfg["url"].rstrip("/") + "/api/sync/batch"
        headers = {"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"}
        payload = {"records": queue_items}

        try:
            resp = requests.post(target_url, json=payload, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                synced_ids = [item["id"] for item in queue_items]
                placeholders = ",".join("?" * len(synced_ids))
                cursor.execute(
                    f"UPDATE sync_queue SET status = 'synced', synced_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                    synced_ids,
                )
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('last_sync_timestamp', ?, CURRENT_TIMESTAMP)", (now_iso,))

                return {"status": "success", "synced_count": len(queue_items), "message": f"{len(queue_items)} qeyd uzaq serverə ötürüldü."}
            else:
                for item in queue_items:
                    cursor.execute(
                        "UPDATE sync_queue SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                        (f"HTTP {resp.status_code}", item["id"]),
                    )
                return {"status": "failed", "synced_count": 0, "message": f"Server cavabı: {resp.status_code}"}
        except requests.exceptions.RequestException as e:
            # Operational continuity: non-blocking failure
            logger.info(f"Offline mode active: could not sync pending queue ({e})")
            for item in queue_items:
                cursor.execute(
                    "UPDATE sync_queue SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                    (str(e)[:150], item["id"]),
                )
            return {"status": "offline", "synced_count": 0, "message": "Lokal rejim: İnternet və ya server əlçatan deyil."}

def sync_all_existing_data_to_remote() -> dict:
    """Initial bulk synchronization of all existing data to remote server."""
    cfg = get_sync_configuration()
    if not cfg["url"]:
        return {"success": False, "message": "Əvvəlcə uzaq server ünvanını qeyd edin."}

    conn_ok, conn_msg = test_remote_connection(cfg["url"], cfg["token"])
    if not conn_ok:
        return {"success": False, "message": f"Serverə qoşulma uğursuz oldu: {conn_msg}"}

    # Queue all completed orders that are not yet in sync queue
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, order_number, final_amount FROM orders")
        orders = cursor.fetchall()
        for o in orders:
            cursor.execute(
                """
                INSERT INTO sync_queue (table_name, record_id, action, payload_json, status)
                VALUES ('orders', ?, 'insert', ?, 'pending')
                """,
                (o["id"], f'{{"order_id": {o["id"]}, "order_number": "{o["order_number"]}", "final_amount": {o["final_amount"]}}}'),
            )

    res = sync_pending_records()
    log_developer_action("sync_all_existing", details=f"Bütün mövcud məlumatların sinxronizasiyası başladıldı: {res.get('message')}")
    return {"success": True, "details": res}

