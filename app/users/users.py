"""
User and Role Management Module
Enforces strict hierarchical permissions (Developer > Admin > Barista),
safe password updates without plaintext disclosure, and custom avatar management.
"""
import logging
import re
from app.core.database import get_db, dict_from_row
from app.auth.auth import hash_password, verify_password
from app.core.audit import log_business_action, log_developer_action
from app.core.avatar import AVATAR_THEMES, avatar_color_for_user, build_avatar_url

logger = logging.getLogger(__name__)

PRESET_AVATARS = [
    {"id": "barista_1", "url": "/static/images/avatar-user.svg", "label": "Barista 1"},
    {"id": "barista_2", "url": "/static/images/avatar-user.svg", "label": "Barista 2"},
    {"id": "barista_3", "url": "/static/images/avatar-user.svg", "label": "Barista 3"},
    {"id": "admin_1", "url": "/static/images/avatar-user.svg", "label": "Admin 1"},
    {"id": "admin_2", "url": "/static/images/avatar-user.svg", "label": "Admin 2"},
]

def list_users(current_user: dict) -> list[dict]:
    """
    List staff accounts based on caller role:
    - Admin: sees ONLY baristas (cannot see Developer or other Admins).
    - Developer: sees all users (Developer, Admins, Baristas).
    - Barista: cannot list users (handled by permission decorator).
    """
    with get_db() as conn:
        cursor = conn.cursor()
        if current_user["role"] == "developer":
            cursor.execute("SELECT id, branch_id, username, full_name, email, role, avatar_url, receipt_signature, is_active, employment_end_at, created_at FROM users ORDER BY role, full_name")
        elif current_user["role"] == "admin":
            cursor.execute("SELECT id, branch_id, username, full_name, email, role, avatar_url, receipt_signature, is_active, employment_end_at, created_at FROM users WHERE role = 'barista' ORDER BY full_name")
        else:
            return []
        return [dict_from_row(r) for r in cursor.fetchall()]

def create_user(current_user: dict, data: dict, ip_address: str = None) -> tuple[dict | None, str]:
    """
    Create a new user account:
    - Developer can create Admin or Barista.
    - Admin can ONLY create Barista.
    """
    role_to_create = data.get("role", "barista").lower()
    if role_to_create not in {"admin", "barista"}:
        return None, "Developer hesabı UI vasitəsilə yaradıla bilməz."

    if current_user["role"] == "admin" and role_to_create != "barista":
        return None, "Admin yalnız Barista hesabı yarada bilər."

    username = str(data.get("username", "")).strip().lower()
    full_name = str(data.get("full_name", "")).strip()
    password = str(data.get("password", "")).strip()
    avatar_theme = str(data.get("avatar_theme", "plain")).lower()
    if avatar_theme not in AVATAR_THEMES:
        avatar_theme = "plain"
    email = str(data.get("email", "")).strip().lower() or None

    if not username or not full_name or not password:
        return None, "İstifadəçi adı, ad-soyad və şifrə mütləq daxil edilməlidir."

    if len(password) < 8:
        return None, "Şifrə ən azı 8 simvol olmalıdır."
    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return None, "E-poçt ünvanı düzgün deyil."

    password_hash = hash_password(password)
    branch_id = current_user.get("branch_id", 1)

    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                return None, f"'{username}' istifadəçi adı artıq mövcuddur."

            cursor.execute(
                """
                INSERT INTO users (branch_id, username, full_name, email, role, password_hash, avatar_url, avatar_color, avatar_theme, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (branch_id, username, full_name, email, role_to_create, password_hash, "", "", avatar_theme),
            )
            new_id = cursor.lastrowid
            color = avatar_color_for_user(new_id)
            avatar_url = build_avatar_url(color, avatar_theme)
            cursor.execute("UPDATE users SET avatar_url = ?, avatar_color = ? WHERE id = ?", (avatar_url, color, new_id))

        log_business_action(
            user_id=current_user["id"],
            username=current_user["username"],
            role=current_user["role"],
            action="create_user",
            entity_type="users",
            entity_id=new_id,
            details=f"Yeni istifadəçi yaradıldı: {username} ({role_to_create})",
            ip_address=ip_address,
        )

        return {"id": new_id, "username": username, "full_name": full_name, "email": email, "role": role_to_create, "avatar_url": avatar_url, "avatar_color": color, "avatar_theme": avatar_theme}, "İstifadəçi uğurla yaradıldı."
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return None, f"Xəta baş verdi: {str(e)}"

def update_user(current_user: dict, target_user_id: int, data: dict, ip_address: str = None) -> tuple[bool, str]:
    """
    Update user info (full_name, avatar_url, is_active, reset password).
    - Developer password cannot be changed here (only from code).
    - Admin can only edit Baristas.
    - Developer can edit Admin or Barista.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (target_user_id,))
        target = cursor.fetchone()
        if not target:
            return False, "İstifadəçi tapılmadı."

        if target["role"] == "developer":
            return False, "Developer şifrəsi və profili UI-dən dəyişdirilə bilməz (Yalnız kod səviyyəsində)."

        if current_user["role"] == "admin" and target["role"] != "barista":
            return False, "Admin yalnız Barista hesablarını redaktə edə bilər."

        full_name = data.get("full_name", target["full_name"])
        avatar_theme = str(data.get("avatar_theme", target["avatar_theme"] or "plain")).lower()
        avatar_theme = avatar_theme if avatar_theme in AVATAR_THEMES else "plain"
        avatar_color = target["avatar_color"] or avatar_color_for_user(target_user_id)
        avatar_url = build_avatar_url(avatar_color, avatar_theme)
        is_active = data.get("is_active", target["is_active"])
        email = str(data.get("email", target["email"] or "")).strip().lower() or None

        new_password = data.get("password")
        if new_password:
            if len(new_password) < 8:
                return False, "Şifrə ən azı 8 simvol olmalıdır."
            if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                return False, "E-poçt ünvanı düzgün deyil."
            pw_hash = hash_password(new_password)
            cursor.execute(
                """
                UPDATE users
                SET full_name = ?, email = ?, avatar_url = ?, avatar_color = ?, avatar_theme = ?, is_active = ?, password_hash = ?, token_version = token_version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (full_name, email, avatar_url, avatar_color, avatar_theme, is_active, pw_hash, target_user_id),
            )
        else:
            cursor.execute(
                """
                UPDATE users
                SET full_name = ?, email = ?, avatar_url = ?, avatar_color = ?, avatar_theme = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (full_name, email, avatar_url, avatar_color, avatar_theme, is_active, target_user_id),
            )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="update_user",
        entity_type="users",
        entity_id=target_user_id,
        details=f"İstifadəçi yeniləndi: {target['username']}",
        ip_address=ip_address,
    )

    return True, "İstifadəçi məlumatları yeniləndi."

def delete_user(current_user: dict, target_user_id: int, ip_address: str = None) -> tuple[bool, str]:
    """Mark an account as terminated while preserving its employment history."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (target_user_id,))
        target = cursor.fetchone()
        if not target:
            return False, "İstifadəçi tapılmadı."

        if target["role"] == "developer":
            return False, "Developer hesabı silinə bilməz."

        if current_user["role"] == "admin" and target["role"] != "barista":
            return False, "Admin yalnız Barista hesabını silə bilər."

        if not target["is_active"]:
            return False, "Bu işçi artıq işdən çıxarılıb."
        cursor.execute(
            """
            UPDATE users
            SET is_active = 0,
                employment_end_at = CURRENT_TIMESTAMP,
                token_version = token_version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (target_user_id,),
        )

    log_business_action(
        user_id=current_user["id"],
        username=current_user["username"],
        role=current_user["role"],
        action="delete_user",
        entity_type="users",
        entity_id=target_user_id,
        details=f"İşçi hesabı işdən çıxarılma kimi deaktiv edildi: {target['username']}",
        ip_address=ip_address,
    )
    return True, "İşçi hesabı işdən çıxarılma kimi deaktiv edildi; tarixçə qorunur."

def update_own_profile(current_user: dict, data: dict) -> tuple[bool, str]:
    """
    Allow any logged-in user to update their own avatar and password.
    CRITICAL: Valid current_password is strictly required to confirm any profile changes.
    """
    user_id = current_user["id"]
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            return False, "İstifadəçi tapılmadı."

        current_pw = str(data.get("current_password", "")).strip()
        if not current_pw or not verify_password(current_pw, user["password_hash"]):
            return False, "Dəyişiklikləri təsdiqləmək üçün cari şifrə mütləq və doğru daxil edilməlidir."

        avatar_theme = str(data.get("avatar_theme", user["avatar_theme"] or "plain")).lower()
        if avatar_theme not in AVATAR_THEMES:
            return False, "Dəstəklənməyən avatar teması."
        avatar_color = user["avatar_color"] or avatar_color_for_user(user_id)
        avatar_url = (
            str(data["avatar_url"]).strip()
            if "avatar_url" in data and "avatar_theme" not in data and data["avatar_url"]
            else build_avatar_url(avatar_color, avatar_theme)
        )
        receipt_signature = str(data.get("receipt_signature", user["receipt_signature"] or "")).strip()[:120] or None
        preferred_language = str(data.get("preferred_language", user["preferred_language"] or "az")).strip().lower()
        if preferred_language not in {"az", "tr", "en", "ru"}:
            return False, "Dəstəklənməyən dil seçimi."
        preferred_theme = str(data.get("preferred_theme", user["preferred_theme"] or "soft-dark")).strip().lower()
        if preferred_theme not in {"light", "soft-dark", "deep-dark", "midnight-glass", "warm-cream", "warm-green", "cool-graphite"}:
            return False, "Dəstəklənməyən tema seçimi."
        preferred_font_size = str(data.get("preferred_font_size", user["preferred_font_size"] or "normal")).strip().lower()
        if preferred_font_size not in {"small", "normal", "large"}:
            return False, "Dəstəklənməyən yazı ölçüsü."

        # If changing password, validate new password
        if data.get("new_password"):
            new_pw = str(data["new_password"]).strip()
            if len(new_pw) < 8:
                return False, "Yeni şifrə ən azı 8 simvol olmalıdır."
            new_hash = hash_password(new_pw)
            cursor.execute(
                "UPDATE users SET avatar_url = ?, avatar_color = ?, avatar_theme = ?, receipt_signature = ?, preferred_language = ?, preferred_theme = ?, preferred_font_size = ?, password_hash = ?, token_version = token_version + 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (avatar_url, avatar_color, avatar_theme, receipt_signature, preferred_language, preferred_theme, preferred_font_size, new_hash, user_id),
            )
        else:
            cursor.execute(
                "UPDATE users SET avatar_url = ?, avatar_color = ?, avatar_theme = ?, receipt_signature = ?, preferred_language = ?, preferred_theme = ?, preferred_font_size = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (avatar_url, avatar_color, avatar_theme, receipt_signature, preferred_language, preferred_theme, preferred_font_size, user_id),
            )

    if data.get("new_password"):
        if current_user["role"] == "developer":
            log_developer_action(
                "developer_password_change",
                details="Developer şifrəsini özü dəyişdi",
            )
        else:
            log_business_action(
                user_id=user_id, username=current_user["username"], role=current_user["role"],
                action="change_password", entity_type="users", entity_id=user_id,
                details="İstifadəçi öz şifrəsini dəyişdi",
            )
    return True, "Profil məlumatlarınız uğurla yeniləndi."


def update_own_language(current_user: dict, language: str) -> tuple[bool, str]:
    """Persist a non-sensitive interface preference without requiring a password."""
    language = str(language or "").strip().lower()
    if language not in {"az", "tr", "en", "ru"}:
        return False, "Dəstəklənməyən dil seçimi."
    with get_db() as conn:
        result = conn.execute(
            "UPDATE users SET preferred_language = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND is_active = 1",
            (language, current_user["id"]),
        )
    return (result.rowcount == 1, "Dil seçimi yadda saxlanıldı." if result.rowcount == 1 else "İstifadəçi tapılmadı.")


def update_own_preferences(current_user: dict, data: dict) -> tuple[bool, str]:
    """Persist non-sensitive display preferences without requiring a password."""
    language = str(data.get("preferred_language", "")).strip().lower()
    theme = str(data.get("preferred_theme", "")).strip().lower()
    font_size = str(data.get("preferred_font_size", "")).strip().lower()
    if language not in {"az", "tr", "en", "ru"}:
        return False, "Dəstəklənməyən dil seçimi."
    if theme not in {"light", "soft-dark", "deep-dark", "midnight-glass", "warm-cream", "warm-green", "cool-graphite"}:
        return False, "Dəstəklənən tema seçilməyib."
    if font_size not in {"small", "normal", "large"}:
        return False, "Dəstəklənməyən yazı ölçüsü."
    with get_db() as conn:
        result = conn.execute(
            "UPDATE users SET preferred_language = ?, preferred_theme = ?, preferred_font_size = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND is_active = 1",
            (language, theme, font_size, current_user["id"]),
        )
    return (result.rowcount == 1, "Profil tənzimləmələri yadda saxlanıldı." if result.rowcount == 1 else "İstifadəçi tapılmadı.")
