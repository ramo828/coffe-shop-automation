"""
Authentication & Session Management Module
Implements GNOME-style user picker endpoints, JWT bearer auth,
bcrypt password hashing, and role-based route guards.
"""
import datetime
import functools
import logging
import jwt
import bcrypt
from flask import request, jsonify, g
from app.core.config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    DEVELOPER_USERNAME,
    INACTIVITY_TIMEOUT_MINUTES,
)
from app.core.database import get_db, dict_from_row
from app.core.audit import log_business_action, log_developer_action

logger = logging.getLogger(__name__)

def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(user_data: dict, expires_delta: datetime.timedelta = None) -> str:
    """Create a signed JWT access token."""
    to_encode = user_data.copy()
    expire = datetime.datetime.now(datetime.timezone.utc) + (
        expires_delta or datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({
        "exp": expire,
        "iat": datetime.datetime.now(datetime.timezone.utc),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str) -> dict | None:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT rejected: expired")
        request.environ["auth_error"] = "expired"
        return None
    except jwt.PyJWTError as e:
        logger.warning("JWT rejected: invalid signature or claims (%s)", e)
        request.environ["auth_error"] = "invalid"
        return None

def get_current_user_from_header() -> dict | None:
    """Extract and authenticate a user from an Authorization Bearer header."""
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        # Avoid an IndexError/500 for a malformed `Bearer` header.
        candidate = auth_header[len("Bearer "):].strip()
        if candidate:
            token = candidate
        else:
            request.environ["auth_error"] = "invalid"
    if not token:
        request.environ["auth_error"] = "missing"
        return None

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        return None

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        request.environ["auth_error"] = "invalid"
        logger.warning("JWT rejected: invalid subject claim")
        return None
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, branch_id, username, full_name, role, avatar_url, avatar_color, avatar_theme, receipt_signature, preferred_language, preferred_theme, preferred_font_size, last_activity_at, is_active, token_version FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            request.environ["auth_error"] = "user_missing"
            logger.warning("JWT rejected: user no longer exists (user_id=%s)", user_id)
            return None
        if row["is_active"] != 1:
            request.environ["auth_error"] = "inactive"
            logger.warning("JWT rejected: user inactive (user_id=%s)", user_id)
            return None
        now = datetime.datetime.now(datetime.timezone.utc)
        last_activity = row["last_activity_at"]
        if last_activity:
            try:
                parsed = datetime.datetime.fromisoformat(str(last_activity).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=datetime.timezone.utc)
                if (now - parsed).total_seconds() > INACTIVITY_TIMEOUT_MINUTES * 60:
                    request.environ["auth_error"] = "inactive_timeout"
                    logger.warning("JWT rejected: inactivity timeout (user_id=%s)", user_id)
                    return None
            except ValueError:
                logger.warning("Invalid last_activity_at for user_id=%s; resetting activity clock", user_id)
        conn.execute("UPDATE users SET last_activity_at = ? WHERE id = ?", (now.isoformat(), user_id))
        if int(payload.get("token_version", row["token_version"])) != int(row["token_version"]):
            request.environ["auth_error"] = "token_version"
            logger.warning("JWT rejected: token version mismatch (user_id=%s)", user_id)
            return None
        return dict_from_row(row)

def require_auth(allowed_roles=None):
    """Decorator to enforce JWT Bearer authentication and role-based access."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            user = get_current_user_from_header()
            if not user:
                reason = request.environ.get("auth_error", "invalid")
                messages = {
                    "expired": "Sessiyanızın vaxtı bitib. Yenidən daxil olun.",
                    "inactive": "Bu istifadəçi hesabı deaktiv edilib.",
                    "token_version": "Sessiya yenilənib. Yenidən daxil olun.",
                    "inactive_timeout": "Sessiyanız uzun müddət fəaliyyətsiz qaldığı üçün bağlanıb. Yenidən daxil olun.",
                    "missing": "Daxil olmaq tələb olunur.",
                }
                return jsonify({"error": messages.get(reason, "Sessiya təsdiqlənmədi. Yenidən daxil olun."), "auth_reason": reason}), 401
            if allowed_roles and user["role"] not in allowed_roles:
                return jsonify({"error": "Bu əməliyyat üçün icazəniz yoxdur"}), 403
            g.current_user = user
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# --- API Service Functions ---

def get_visible_profiles_service() -> list[dict]:
    """
    Returns visible user profile cards for the GNOME-style picker.
    CRITICAL RULE D3: Developer account must NOT appear in the visible profile list!
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, full_name, role, avatar_url
            FROM users
            WHERE role != 'developer' AND is_active = 1
            ORDER BY CASE WHEN role = 'admin' THEN 0 ELSE 1 END, full_name ASC
            """
        )
        rows = cursor.fetchall()
        return [dict_from_row(r) for r in rows]

def login_by_profile_service(user_id: int, password: str, ip_address: str = None) -> tuple[dict | None, str]:
    """Authenticate a user selected from GNOME profile card."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,))
        user = cursor.fetchone()
        if not user:
            return None, "İstifadəçi tapılmadı və ya deaktivdir."

        # Developer cannot be logged in via profile card
        if user["role"] == "developer":
            return None, "Bu hesab yalnız xüsusi giriş paneli vasitəsilə daxil ola bilər."

        if not verify_password(password, user["password_hash"]):
            return None, "Şifrə yalnışdır."

        login_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute("UPDATE users SET last_activity_at = ? WHERE id = ?", (login_time, user["id"]))
        conn.commit()

        token = create_access_token({
            "sub": str(user["id"]),
            "username": user["username"],
            "role": user["role"],
            "full_name": user["full_name"],
            "branch_id": user["branch_id"],
            "token_version": user["token_version"],
            "preferred_language": user["preferred_language"] or "az",
            "preferred_theme": user["preferred_theme"] or "soft-dark",
            "preferred_font_size": user["preferred_font_size"] or "normal",
            "avatar_color": user["avatar_color"],
            "avatar_theme": user["avatar_theme"] or "plain",
        })

        log_business_action(
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
            action="login_profile",
            details="GNOME profil kartı ilə giriş edildi",
            ip_address=ip_address,
        )

        return {
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"],
                "avatar_url": user["avatar_url"],
                "branch_id": user["branch_id"],
                "token_version": user["token_version"],
                "preferred_language": user["preferred_language"] or "az",
                "preferred_theme": user["preferred_theme"] or "soft-dark",
                "preferred_font_size": user["preferred_font_size"] or "normal",
                "avatar_color": user["avatar_color"],
                "avatar_theme": user["avatar_theme"] or "plain",
            }
        }, "Uğurla daxil olundu."

def login_other_service(username: str, password: str, ip_address: str = None) -> tuple[dict | None, str]:
    """
    Authenticate via manual username + password ("Other" / "Digər" option).
    Developer logs in here.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username.strip(),))
        user = cursor.fetchone()
        if not user:
            return None, "İstifadəçi adı və ya şifrə yalnışdır."

        if not verify_password(password, user["password_hash"]):
            return None, "İstifadəçi adı və ya şifrə yalnışdır."

        login_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.execute("UPDATE users SET last_activity_at = ? WHERE id = ?", (login_time, user["id"]))
        conn.commit()

        token = create_access_token({
            "sub": str(user["id"]),
            "username": user["username"],
            "role": user["role"],
            "full_name": user["full_name"],
            "branch_id": user["branch_id"],
            "preferred_language": user["preferred_language"] or "az",
            "preferred_theme": user["preferred_theme"] or "soft-dark",
            "preferred_font_size": user["preferred_font_size"] or "normal",
            "avatar_color": user["avatar_color"],
            "avatar_theme": user["avatar_theme"] or "plain",
            "preferred_theme": user["preferred_theme"] or "soft-dark",
            "avatar_color": user["avatar_color"],
            "avatar_theme": user["avatar_theme"] or "plain",
            "token_version": user["token_version"],
        })

        if user["role"] == "developer":
            log_developer_action("developer_login", details="Developer 'Digər' paneli vasitəsilə daxil oldu", ip_address=ip_address)
        else:
            log_business_action(
                user_id=user["id"],
                username=user["username"],
                role=user["role"],
                action="login_other",
                details="'Digər' forması ilə daxil olundu",
                ip_address=ip_address,
            )

        return {
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"],
                "avatar_url": user["avatar_url"],
                "branch_id": user["branch_id"],
                "preferred_language": user["preferred_language"] or "az",
            }
        }, "Uğurla daxil olundu."
