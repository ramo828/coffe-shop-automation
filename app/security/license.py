"""
License, Trial & Activation Management
Enforces the 7-day trial Demo mode, anti-tamper lockouts, and
cryptographic HMAC-SHA256 activation keys for REAL mode.
"""
import hmac
import hashlib
import datetime
import logging
import os
from app.core.config import TRIAL_DURATION_DAYS, LICENSE_SALT, DEFAULT_BRANCH_CODE, APP_SECRET
from app.core.database import get_db
from app.security.time_guard import check_time_integrity, is_tamper_flagged

logger = logging.getLogger(__name__)

MASTER_DEVELOPER_SIGNING_SECRET = f"{APP_SECRET}:license-signing"

def generate_activation_key(branch_code: str = DEFAULT_BRANCH_CODE) -> str:
    """
    Generate a cryptographic REAL mode activation key for a given branch.
    Only Developer role has access to this tool.
    """
    msg = f"BRANCH:{branch_code}:ILLY_COFFEE_AUTHENTIC_2026:{LICENSE_SALT}".encode("utf-8")
    sig = hmac.new(MASTER_DEVELOPER_SIGNING_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    # Format: ILLY-REAL-{BRANCH_CODE}-{16_HEX_CHARS_UPPERCASE}
    code_part = branch_code.upper().replace(" ", "-")
    return f"ILLY-REAL-{code_part}-{sig[:16].upper()}"

def verify_activation_key(key: str, branch_code: str = DEFAULT_BRANCH_CODE) -> bool:
    """Verify cryptographic authenticity of an activation key."""
    if not key or not isinstance(key, str):
        return False
    expected_key = generate_activation_key(branch_code)
    return hmac.compare_digest(key.strip().upper(), expected_key.upper())

def get_system_license_status() -> dict:
    """
    Evaluate system license state:
    Returns dict with:
    - is_real_mode: bool
    - is_locked: bool
    - trial_days_left: float
    - trial_expired: bool
    - tamper_detected: bool
    - status_label: 'REAL', 'TRIAL_ACTIVE', 'TRIAL_EXPIRED', 'TAMPER_LOCKED'
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM system_settings WHERE key IN ('is_real_mode', 'activation_key', 'trial_start_date', 'tamper_detected', 'tamper_reason')")
        settings = {row[0]: row[1] for row in cursor.fetchall()}

    # Check REAL mode first
    is_real = settings.get("is_real_mode") == "1"
    activation_key = settings.get("activation_key", "")
    if is_real and verify_activation_key(activation_key):
        return {
            "is_real_mode": True,
            "is_locked": False,
            "trial_days_left": None,
            "trial_expired": False,
            "tamper_detected": False,
            "status_label": "REAL",
            "message": "REAL rejim aktivdir. Lisenziya daimidir.",
        }

    # Check clock tampering
    time_valid, reason = check_time_integrity()
    if not time_valid or is_tamper_flagged():
        return {
            "is_real_mode": False,
            "is_locked": True,
            "trial_days_left": 0,
            "trial_expired": True,
            "tamper_detected": True,
            "status_label": "TAMPER_LOCKED",
            "message": f"Sistem bloklandı: Saat manipulyasiyası aşkarlandı. ({reason})",
        }

    # Evaluate 7-day trial
    trial_start_str = settings.get("trial_start_date")
    try:
        trial_start = datetime.datetime.fromisoformat(trial_start_str.replace("Z", "+00:00"))
        if trial_start.tzinfo is None:
            trial_start = trial_start.replace(tzinfo=datetime.timezone.utc)
    except Exception:
        trial_start = datetime.datetime.now(datetime.timezone.utc)

    now = datetime.datetime.now(datetime.timezone.utc)
    elapsed_seconds = (now - trial_start).total_seconds()
    total_trial_seconds = TRIAL_DURATION_DAYS * 86400

    if elapsed_seconds >= total_trial_seconds:
        return {
            "is_real_mode": False,
            "is_locked": True,
            "trial_days_left": 0,
            "trial_expired": True,
            "tamper_detected": False,
            "status_label": "TRIAL_EXPIRED",
            "message": "7 günlük sınaq müddəti bitdi. REAL rejimə keçid üçün Developer açarı daxil edin.",
        }

    days_left = max(0.0, round((total_trial_seconds - elapsed_seconds) / 86400, 1))
    return {
        "is_real_mode": False,
        "is_locked": False,
        "trial_days_left": max(0.0, days_left),
        "trial_expired": False,
        "tamper_detected": False,
        "status_label": "TRIAL_ACTIVE",
        "message": f"Demo Sınaq Rejimi: {days_left} gün qalıb.",
    }

def activate_real_mode(activation_key: str, branch_code: str = DEFAULT_BRANCH_CODE) -> tuple[bool, str]:
    """Activate REAL mode using provided developer key."""
    if not verify_activation_key(activation_key, branch_code):
        return False, "Yalnış və ya etibarsız Developer aktivasiya açarı."

    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('is_real_mode', '1', CURRENT_TIMESTAMP)")
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('activation_key', ?, CURRENT_TIMESTAMP)", (activation_key.strip(),))
        conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('tamper_detected', '0', CURRENT_TIMESTAMP)")

    logger.info("REAL mode successfully activated!")
    return True, "REAL rejim uğurla aktivləşdirildi!"
