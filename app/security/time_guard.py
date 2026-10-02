"""
Time Guard and Anti-Tamper Module
Ensures trial validity by cross-checking local monotonic events,
stored audit timestamps, and remote internet time when available.
"""
import datetime
import logging
import requests
from app.core.database import get_db

logger = logging.getLogger(__name__)

TIME_SERVERS = [
    "https://worldtimeapi.org/api/timezone/Etc/UTC",
    "https://www.google.com",
    "https://www.cloudflare.com",
]

def get_latest_recorded_timestamp() -> datetime.datetime:
    """Find the most recent timestamp recorded in the database."""
    latest = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            queries = [
                "SELECT max(created_at) FROM orders",
                "SELECT max(created_at) FROM shifts",
                "SELECT max(created_at) FROM audit_logs",
                "SELECT max(updated_at) FROM system_settings",
            ]
            for q in queries:
                cursor.execute(q)
                row = cursor.fetchone()
                if row and row[0]:
                    try:
                        # Handle ISO format or standard SQLite timestamp
                        ts_str = str(row[0]).replace("Z", "+00:00")
                        dt = datetime.datetime.fromisoformat(ts_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=datetime.timezone.utc)
                        if dt > latest:
                            latest = dt
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Error querying latest recorded timestamp: {e}")
    return latest

def fetch_network_time() -> datetime.datetime | None:
    """Attempt to fetch trusted internet time without blocking execution."""
    for url in TIME_SERVERS:
        try:
            resp = requests.head(url, timeout=2.0)
            if "Date" in resp.headers:
                # Format: "Sun, 06 Sep 2026 08:35:22 GMT"
                from email.utils import parsedate_to_datetime
                return parsedate_to_datetime(resp.headers["Date"])
        except Exception:
            continue
    return None

def check_time_integrity() -> tuple[bool, str]:
    """
    Validate that the clock has not been rolled backward to tamper with trial.
    Returns: (is_valid, reason)
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    latest_db_time = get_latest_recorded_timestamp()

    # Rule: If current time is earlier than the latest event in DB by more than 15 minutes,
    # someone rolled the system clock back!
    if (latest_db_time - now).total_seconds() > 900:
        reason = f"Saat manipulyasiyası aşkarlandı: Sistem vaxtı ({now.isoformat()}) verilənlər bazasındakı son əməliyyat vaxtından ({latest_db_time.isoformat()}) geridədir."
        record_tamper_event(reason)
        return False, reason

    # Check network time if available
    net_time = fetch_network_time()
    if net_time:
        diff_seconds = abs((net_time - now).total_seconds())
        # Allow up to 1 hour timezone/skew discrepancy before flagging tamper
        if diff_seconds > 3600:
            reason = f"Şəbəkə vaxtı ilə uyğunsuzluq: İnternet vaxtı ({net_time.isoformat()}), cihaz vaxtı ({now.isoformat()})."
            record_tamper_event(reason)
            return False, reason

    return True, "Vaxt tamlığı təsdiqləndi."

def record_tamper_event(reason: str):
    """Mark system as tampered in settings."""
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('tamper_detected', '1', CURRENT_TIMESTAMP)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('tamper_reason', ?, CURRENT_TIMESTAMP)",
                (reason,),
            )
    except Exception as e:
        logger.error(f"Failed to record tamper state: {e}")

def is_tamper_flagged() -> bool:
    """Check if tamper flag has been set."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_settings WHERE key = 'tamper_detected'")
            row = cursor.fetchone()
            return bool(row and row[0] == "1")
    except Exception:
        return False
