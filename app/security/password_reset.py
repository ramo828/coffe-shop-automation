"""Secure password-reset and optional SMTP/Bore delivery services."""
import datetime
import hashlib
import logging
import secrets
import smtplib
import ssl
import subprocess
import threading
import time
import re
import selectors
from email.message import EmailMessage
from urllib.parse import quote

from app.auth.auth import hash_password
from app.core.config import (
    BORE_BIN, BORE_ENABLED, BORE_LOCAL_PORT,  BORE_SERVER,
    PASSWORD_RESET_TOKEN_MINUTES, SMTP_FROM, SMTP_HOST, SMTP_PASSWORD,
    SMTP_PORT, SMTP_USE_TLS, SMTP_USERNAME,
)
from app.core.database import get_db

logger = logging.getLogger(__name__)
_bore_process = None
_bore_lock = threading.Lock()
_reset_attempts = {}
_reset_attempts_lock = threading.Lock()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _start_bore() -> str | None:
    global _bore_process
    if not BORE_ENABLED:
        return None
    with _bore_lock:
        if _bore_process and _bore_process.poll() is None:
            return getattr(_bore_process, "public_url", None)
        try:
            _bore_process = subprocess.Popen(
                [BORE_BIN, "local", str(BORE_LOCAL_PORT), "--to", BORE_SERVER],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            selector = selectors.DefaultSelector()
            if _bore_process.stdout:
                selector.register(_bore_process.stdout, selectors.EVENT_READ)
            events = selector.select(timeout=5)
            line = events[0][0].fileobj.readline() if events else ""
            selector.close()
            match = re.search(r"(?:https?://)?([A-Za-z0-9.-]+):(\d+)", line)
            if match and "listen" in line.lower():
                public_url = f"https://{match.group(1)}:{match.group(2)}"
                _bore_process.public_url = public_url
                timer = threading.Timer(900, _stop_bore)
                timer.daemon = True
                timer.start()
                logger.info("Bore reset tunnel available at %s", public_url)
                return public_url
            _terminate_bore_process()
        except (OSError, ValueError) as exc:
            logger.warning("Bore tunnel unavailable; using local reset URL: %s", exc)
            _terminate_bore_process()
    return None


def _terminate_bore_process() -> None:
    global _bore_process
    if _bore_process and _bore_process.poll() is None:
        _bore_process.terminate()
        try:
            _bore_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _bore_process.kill()
    _bore_process = None


def _stop_bore() -> None:
    global _bore_process
    with _bore_lock:
        _terminate_bore_process()


def _configured_mail() -> dict:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT key, value FROM system_settings WHERE key IN ('smtp_host','smtp_port','smtp_username','smtp_password','smtp_from','smtp_use_tls')"
        ).fetchall()
    values = {row["key"]: row["value"] for row in rows}
    return {
        "host": values.get("smtp_host") or SMTP_HOST,
        "port": int(values.get("smtp_port") or SMTP_PORT),
        "username": values.get("smtp_username") or SMTP_USERNAME,
        "password": values.get("smtp_password") or SMTP_PASSWORD,
        "from": values.get("smtp_from") or SMTP_FROM,
        "use_tls": (values.get("smtp_use_tls", "1").lower() not in {"0", "false", "no"}),
    }


def _send_email(recipient: str, subject: str, body: str) -> None:
    settings = _configured_mail()
    if not settings["host"] or not settings["from"]:
        raise RuntimeError("SMTP ayarları tamamlanmayıb.")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings["from"]
    message["To"] = recipient
    message.set_content(body)
    with smtplib.SMTP(settings["host"], settings["port"], timeout=10) as server:
        if settings["use_tls"]:
            server.starttls(context=ssl.create_default_context())
        if settings["username"]:
            server.login(settings["username"], settings["password"])
        server.send_message(message)


def get_mail_settings() -> dict:
    settings = _configured_mail()
    return {
        "smtp_host": settings["host"],
        "smtp_port": settings["port"],
        "smtp_username": settings["username"],
        "smtp_from": settings["from"],
        "smtp_use_tls": settings["use_tls"],
        "bore_enabled": BORE_ENABLED,
        "bore_public_url": None,
    }


def save_mail_settings(data: dict) -> tuple[bool, str]:
    host = str(data.get("smtp_host", "")).strip()
    try:
        port = int(data.get("smtp_port", SMTP_PORT))
    except (TypeError, ValueError):
        return False, "SMTP portu düzgün rəqəm olmalıdır."
    if host and not 1 <= port <= 65535:
        return False, "SMTP portu 1-65535 aralığında olmalıdır."
    values = {
        "smtp_host": host,
        "smtp_port": str(port),
        "smtp_username": str(data.get("smtp_username", "")).strip(),
        "smtp_from": str(data.get("smtp_from", "")).strip(),
        "smtp_use_tls": "1" if bool(data.get("smtp_use_tls", True)) else "0",
    }
    password = data.get("smtp_password")
    if password is not None and str(password):
        values["smtp_password"] = str(password)
    with get_db() as conn:
        for key, value in values.items():
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (key, value))
    return True, "SMTP ayarları saxlanıldı."


def request_password_reset(identifier: str, base_url: str, requested_by: dict | None, ip_address: str | None) -> tuple[bool, str]:
    now_epoch = time.time()
    with _reset_attempts_lock:
        recent = [stamp for stamp in _reset_attempts.get(ip_address or "unknown", []) if now_epoch - stamp < 900]
        if len(recent) >= 5:
            return False, "Çox sayda sorğu göndərildi. 15 dəqiqə sonra yenidən cəhd edin."
        recent.append(now_epoch)
        _reset_attempts[ip_address or "unknown"] = recent
    identifier = (identifier or "").strip().lower()
    now = datetime.datetime.now(datetime.timezone.utc)
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, email FROM users WHERE is_active = 1 AND (lower(username) = ? OR lower(COALESCE(email, '')) = ?)",
            (identifier, identifier),
        ).fetchone()
        if not row or not row["email"]:
            return True, "Əgər bu istifadəçi üçün e-poçt qeydiyyatlıdırsa, reset bağlantısı göndərildi."
        raw_token = secrets.token_urlsafe(32)
        expires = now + datetime.timedelta(minutes=PASSWORD_RESET_TOKEN_MINUTES)
        conn.execute(
            "UPDATE password_reset_tokens SET used_at = CURRENT_TIMESTAMP WHERE user_id = ? AND used_at IS NULL",
            (row["id"],),
        )
        conn.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, requested_by, requested_ip) VALUES (?, ?, ?, ?, ?)",
            (row["id"], _token_hash(raw_token), expires.isoformat(), (requested_by or {}).get("id"), ip_address),
        )
    public_base = _start_bore() or base_url.rstrip("/")
    link = f"{public_base}/?reset_token={quote(raw_token)}"
    try:
        _send_email(row["email"], "Coffee Shop şifrə sıfırlama bağlantısı", f"Bu bağlantı 15 dəqiqə ərzində və yalnız bir dəfə işləyir:\n\n{link}\n")
    except Exception as exc:
        logger.error("Password reset email delivery failed: %s", exc)
        return False, "Reset e-poçtu göndərilə bilmədi. SMTP ayarlarını yoxlayın."
    return True, "Əgər bu istifadəçi üçün e-poçt qeydiyyatlıdırsa, reset bağlantısı göndərildi."


def reset_password(raw_token: str, new_password: str) -> tuple[bool, str]:
    if not raw_token or len(new_password or "") < 8:
        return False, "Reset bağlantısı və ən azı 8 simvolluq yeni şifrə tələb olunur."
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, user_id FROM password_reset_tokens WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
            (_token_hash(raw_token), now),
        ).fetchone()
        if not row:
            return False, "Reset bağlantısı etibarsızdır və ya müddəti bitib."
        conn.execute("UPDATE users SET password_hash = ?, token_version = token_version + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (hash_password(new_password), row["user_id"]))
        conn.execute("UPDATE password_reset_tokens SET used_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
    _stop_bore()
    return True, "Şifrə yeniləndi. İndi yeni şifrənizlə daxil olun."
