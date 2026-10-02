"""
Main Flask Application Factory and API Routes
Illy-Style Specialty Coffee Shop Management System
"""
import os
import sys
import threading
import logging
import re
import json
import sqlite3
import time
import uuid
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict, deque
from flask import Flask, request, jsonify, send_from_directory, send_file, Response, g
from io import BytesIO
from werkzeug.exceptions import BadRequest

from app.core.config import BASE_DIR, DB_PATH, BACKUP_DIR, IS_PRODUCTION, DEFAULT_BRANCH_ID, DEFAULT_BRANCH_NAME, DEFAULT_BRANCH_CODE
from app.core.database import init_db, get_db, consume_rate_limit
from app.core.alerts import get_alert_summary, list_alerts, acknowledge_alert
from app.core.backup import create_backup, restore_backup, check_integrity, vacuum_database, list_backups, create_daily_backup
from app.auth.auth import hash_password
from app.auth.auth import (
    require_auth,
    get_visible_profiles_service,
    login_by_profile_service,
    login_other_service,
)
from app.users.users import (
    list_users,
    create_user,
    update_user,
    delete_user,
    update_own_profile, update_own_language, update_own_preferences,
)
from app.products.products import (
    list_products,
    reorder_products,
    create_product,
    update_product,
    delete_product,
    add_product_variant,
    delete_product_variant,
)
from app.recipes.recipes import (
    get_recipe_for_variant,
    set_recipe_for_variant,
    delete_recipe_ingredient,
    clear_variant_recipe,
)
from app.stock.raw_materials import (
    list_raw_materials,
    create_raw_material,
    update_raw_material,
    delete_raw_material,
    restock_raw_material,
)
from app.orders.orders import (
    create_order,
    cancel_order,
    format_internal_ticket,
    list_recent_orders,
)
from app.cash_movements import create_cash_movement, list_cash_movements
from app.orders.shortcuts import (
    get_user_shortcuts,
    set_user_shortcuts,
    add_user_shortcut,
    update_user_shortcut,
    remove_user_shortcut,
    reorder_user_shortcuts,
)
from app.shifts.shifts import (
    get_active_shift,
    open_shift,
    close_shift,
    list_shifts,
    get_shift_details,
    auto_close_forgotten_shifts,
)
from app.inventory.inventory import (
    start_inventory_session,
    get_inventory_session,
    update_inventory_counts,
    confirm_inventory_adjustments,
    list_inventory_sessions,
)
from app.reports.reports import (
    get_sales_overview,
    get_sales_report,
    get_daily_sales_chart,
    get_hourly_sales_traffic,
    get_top_selling_products,
    get_barista_performance,
    get_stock_depletion_overview,
    get_employee_report,
    build_sales_export,
    get_end_of_day_report,
)
from app.ml.ml_engine import (
    generate_business_recommendations,
    get_developer_ml_metrics,
    train_or_update_ml_models,
)
from app.core.retention import (
    get_current_retention_policy,
    set_retention_policy,
    execute_retention_cleanup,
)
from app.sync.sync_engine import (
    get_sync_configuration,
    update_sync_configuration,
    test_remote_connection,
    sync_pending_records,
    sync_all_existing_data_to_remote,
)
from app.sync.remote_packager import generate_remote_code_zip
from app.developer.developer import (
    get_system_diagnostics,
    update_system_branding,
    set_encryption_mode,
    set_compression_mode,
    list_developer_audit_logs,
    export_db_sql,
    export_db_json,
    export_db_tree_txt,
)
from app.security.license import (
    get_system_license_status,
    activate_real_mode,
    generate_activation_key,
    verify_activation_key,
)
from app.security.password_reset import (
    get_mail_settings,
    request_password_reset,
    reset_password,
    save_mail_settings,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)
_SHIFT_HOUSEKEEPING_STARTED = False

def create_app():
    global _SHIFT_HOUSEKEEPING_STARTED
    static_folder = str(BASE_DIR / "app" / "static")
    app = Flask(__name__, static_folder=static_folder, static_url_path="/static")
    if not os.environ.get("PYTEST_CURRENT_TEST") and not _SHIFT_HOUSEKEEPING_STARTED:
        _SHIFT_HOUSEKEEPING_STARTED = True
        def shift_housekeeping():
            while True:
                try:
                    import datetime as _datetime
                    now = _datetime.datetime.now(_datetime.timezone.utc)
                    if now.hour == 0 and now.minute >= 5:
                        auto_close_forgotten_shifts(now=now)
                        time.sleep(60)
                    else:
                        time.sleep(30)
                except Exception:
                    logger.exception("Shift housekeeping loop failed")
                    time.sleep(60)
        threading.Thread(target=shift_housekeeping, name="shift-housekeeping", daemon=True).start()
    rate_limited_paths = {
        "/api/auth/login-profile": (10, 900),
        "/api/auth/login-other": (10, 900),
        "/api/auth/forgot-password": (5, 900),
        "/api/auth/reset-password": (10, 900),
        "/api/developer/password": (5, 900),
        "/api/developer/export/sql": (20, 60),
        "/api/developer/export/json": (20, 60),
        "/api/developer/export/txt": (20, 60),
        "/api/sync/download-package": (10, 60),
    }

    @app.before_request
    def request_context():
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        if request.path in rate_limited_paths:
            limit, window = rate_limited_paths[request.path]
            allowed, retry_after = consume_rate_limit(
                f"{request.remote_addr or 'unknown'}:{request.path}", limit, window
            )
            if not allowed:
                response = jsonify({"error": "Too many requests", "request_id": g.request_id})
                response.status_code = 429
                response.headers["Retry-After"] = str(retry_after)
                return response

    @app.after_request
    def add_security_headers(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", uuid.uuid4().hex)
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if request.path.startswith("/static/uploads/"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'",
            )
        if request.path == "/" or request.path.startswith(("/static/", "/css/", "/js/")) or request.path == "/api/auth/reset-password":
            response.headers.setdefault("Cache-Control", "no-store")
        logger.info(json.dumps({
            "event": "http_request", "request_id": getattr(g, "request_id", None),
            "method": request.method, "path": request.path, "status": response.status_code,
            "remote_addr": request.remote_addr,
        }, separators=(",", ":")))
        return response

    @app.errorhandler(BadRequest)
    def handle_bad_request(error):
        """Keep malformed JSON and other client errors consistently machine-readable."""
        return jsonify({
            "error": "Sorğu düzgün deyil.",
            "request_id": getattr(g, "request_id", None),
        }), 400

    @app.route("/api/health", methods=["GET"])
    def health():
        integrity = check_integrity()
        usage = shutil.disk_usage(str(BASE_DIR))
        backups = list_backups()
        return jsonify({
            "status": "ok" if integrity["ok"] else "degraded",
            "database": integrity,
            "disk": {"free_bytes": usage.free, "total_bytes": usage.total},
            "last_backup": backups[0] if backups else None,
            "version": os.environ.get("COFFEE_APP_VERSION", "2026.09"),
            "request_id": g.request_id,
        }), (200 if integrity["ok"] else 503)

    # Initialize database tables & seed bootstrap developer
    init_db()
    try:
        create_daily_backup()
    except Exception:
        logger.exception("Daily backup initialization failed")

    def setup_status():
        with get_db() as conn:
            rows = conn.execute("SELECT key, value FROM system_settings WHERE key IN ('setup_completed', 'shop_name', 'shop_tagline', 'logo_url', 'banner_url')").fetchall()
            active_staff = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role IN ('admin', 'barista') AND is_active = 1").fetchone()["c"]
        settings = {row["key"]: row["value"] for row in rows}
        license_state = get_system_license_status()
        demo_mode = not IS_PRODUCTION and not license_state.get("is_real_mode")
        completed = settings.get("setup_completed") == "1" and active_staff > 0
        return {
            "completed": completed,
            "demo_mode": demo_mode,
            # Setup is a one-time bootstrap flow. Demo mode must not reopen
            # account creation after the first successful setup.
            "available": not completed and active_staff == 0,
            "shop_name": settings.get("shop_name", DEFAULT_BRANCH_NAME),
            "shop_tagline": settings.get("shop_tagline", "Daxili Nəzarət və Anbar İdarəetməsi"),
            "logo_url": (
                "/static/images/illy-logo.svg"
                if settings.get("logo_url") and not str(settings.get("logo_url", "")).endswith(".svg")
                else settings.get("logo_url", "/static/images/illy-logo.svg")
            ),
            "banner_url": settings.get("banner_url", ""),
        }

    @app.route("/api/branches", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer", "barista"])
    def branches_list():
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, name, code, address, created_at FROM branches ORDER BY id"
            ).fetchall()
        return jsonify([dict(row) for row in rows])

    @app.route("/api/branches", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def branches_create():
        data = request.get_json(silent=True) or {}
        name, code = str(data.get("name", "")).strip(), str(data.get("code", "")).strip()
        if not name or not code:
            return jsonify({"error": "Filial adı və kodu tələb olunur."}), 400
        try:
            with get_db() as conn:
                cursor = conn.execute(
                    "INSERT INTO branches (name, code, address) VALUES (?, ?, ?)",
                    (name, code, str(data.get("address", "")).strip() or None),
                )
                branch_id = cursor.lastrowid
            return jsonify({"id": branch_id, "name": name, "code": code}), 201
        except sqlite3.IntegrityError:
            return jsonify({"error": "Bu filial kodu artıq mövcuddur."}), 409

    # --- UI Shell Routes ---
    @app.route("/")
    def index():
        return send_from_directory(static_folder, "index.html")

    # Relative asset aliases keep the same UI working when the static folder
    # is opened through a simple local web server as well as through Flask.
    @app.route("/css/<path:filename>")
    def css_assets(filename):
        return send_from_directory(os.path.join(static_folder, "css"), filename)

    @app.route("/js/<path:filename>")
    def js_assets(filename):
        return send_from_directory(os.path.join(static_folder, "js"), filename)

    # --- License & Trial Guard ---
    @app.route("/api/license/status", methods=["GET"])
    def license_status():
        return jsonify(get_system_license_status())

    @app.route("/api/license/activate", methods=["POST"])
    def license_activate():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "Sorğu JSON obyekti olmalıdır."}), 400
        key = str(data.get("key", "")).strip()
        success, msg = activate_real_mode(key)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/setup/status", methods=["GET"])
    def setup_status_route():
        return jsonify(setup_status())

    @app.route("/api/setup/complete", methods=["POST"])
    def setup_complete_route():
        current = setup_status()
        if current["completed"]:
            return jsonify({"success": True, "created_users": 0, "message": "Quraşdırma artıq tamamlanıb. Heç bir istifadəçi yenidən yaradılmadı."}), 200
        if not current["available"]:
            return jsonify({"error": "Quraşdırma artıq tamamlanıb və kilidlənib."}), 403
        data = request.get_json(silent=True) or {}
        key = str(data.get("license_key", "")).strip()
        demo_key_allowed = not IS_PRODUCTION and key == "DEMO-SETUP"
        if not key or (not demo_key_allowed and not verify_activation_key(key)):
            return jsonify({"error": "Etibarlı lisenziya açarı daxil edin. Demo üçün DEMO-SETUP istifadə edin."}), 400
        users = data.get("users") or []
        if not isinstance(users, list) or not users:
            return jsonify({"error": "Ən azı bir admin və ya barista hesabı yaradılmalıdır."}), 400
        shop_name = str(data.get("shop_name", "")).strip()
        if not shop_name:
            return jsonify({"error": "Mağaza adı mütləq daxil edilməlidir."}), 400
        logo_url = str(data.get("logo_url", "/static/images/illy-logo.svg")).strip()
        if not (logo_url.startswith("/static/") or logo_url.startswith("data:image/")):
            return jsonify({"error": "Logo seçimi etibarlı deyil."}), 400
        banner_url = str(data.get("banner_url", "")).strip()
        if banner_url and not (banner_url.startswith("/static/") or banner_url.startswith("data:image/")):
            return jsonify({"error": "Banner seçimi etibarlı deyil."}), 400
        # Validate the complete payload before opening a write transaction.  A
        # return from inside get_db() still commits the context manager, which
        # could otherwise leave earlier users persisted when a later user is
        # malformed or duplicated.
        validated_users = []
        seen_usernames = set()
        for item in users:
            if not isinstance(item, dict):
                return jsonify({"error": "İstifadəçi məlumatları düzgün formatda deyil."}), 400
            role = str(item.get("role", "barista")).lower()
            username = str(item.get("username", "")).strip().lower()
            full_name = str(item.get("full_name", "")).strip()
            password = str(item.get("password", "")).strip()
            email = str(item.get("email", "")).strip().lower() or None
            avatar_url = item.get("avatar_url") or "/static/images/avatar-user.svg"
            if role not in {"admin", "barista"} or not username or not full_name or len(password) < 8:
                return jsonify({"error": "İstifadəçi məlumatları natamamdır; rol, ad, istifadəçi adı və ən azı 8 simvolluq şifrə tələb olunur."}), 400
            if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                return jsonify({"error": f"'{username}' üçün e-poçt ünvanı düzgün deyil."}), 400
            if username in seen_usernames:
                return jsonify({"error": f"'{username}' istifadəçi adı təkrar göstərilib."}), 400
            seen_usernames.add(username)
            if not (str(avatar_url).startswith("/static/") or str(avatar_url).startswith("data:image/")):
                return jsonify({"error": f"'{username}' üçün avatar seçimi etibarlı deyil."}), 400
            validated_users.append((username, full_name, email, role, password, avatar_url))

        created = []
        with get_db() as conn:
            existing = {
                row["username"]
                for row in conn.execute(
                    "SELECT username FROM users WHERE username IN ({})".format(
                        ",".join("?" for _ in validated_users)
                    ),
                    tuple(user[0] for user in validated_users),
                ).fetchall()
            }
            if existing:
                username = sorted(existing)[0]
                return jsonify({"error": f"'{username}' istifadəçi adı artıq mövcuddur."}), 400
            for username, full_name, email, role, password, avatar_url in validated_users:
                cursor = conn.execute(
                    "INSERT INTO users (branch_id, username, full_name, email, role, password_hash, avatar_url, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                    (DEFAULT_BRANCH_ID, username, full_name, email, role, hash_password(password), avatar_url),
                )
                created.append(cursor.lastrowid)
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('shop_name', ?, CURRENT_TIMESTAMP)", (shop_name,))
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('shop_tagline', ?, CURRENT_TIMESTAMP)", (str(data.get("shop_tagline", "")).strip(),))
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('logo_url', ?, CURRENT_TIMESTAMP)", (logo_url,))
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('banner_url', ?, CURRENT_TIMESTAMP)", (banner_url,))
            if key != "DEMO-SETUP":
                conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('is_real_mode', '1', CURRENT_TIMESTAMP)")
                conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('activation_key', ?, CURRENT_TIMESTAMP)", (key,))
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('setup_completed', '1', CURRENT_TIMESTAMP)")
        return jsonify({"success": True, "created_users": len(created), "message": "Quraşdırma tamamlandı. Giriş səhifəsinə yönləndirilirsiniz."})

    # --- Auth & GNOME User Picker ---
    @app.route("/api/auth/profiles", methods=["GET"])
    def auth_profiles():
        """Visible profiles for GNOME picker. Excludes Developer."""
        profiles = get_visible_profiles_service()
        return jsonify(profiles)

    @app.route("/api/auth/login-profile", methods=["POST"])
    def auth_login_profile():
        data = request.get_json(force=True) or {}
        user_id = data.get("user_id")
        password = data.get("password", "")
        ip = request.remote_addr
        result, msg = login_by_profile_service(user_id, password, ip)
        if not result:
            return jsonify({"error": msg}), 401
        return jsonify(result)

    @app.route("/api/auth/login-other", methods=["POST"])
    def auth_login_other():
        data = request.get_json(force=True) or {}
        username = data.get("username", "")
        password = data.get("password", "")
        ip = request.remote_addr
        result, msg = login_other_service(username, password, ip)
        if not result:
            return jsonify({"error": msg}), 401
        return jsonify(result)

    @app.route("/api/auth/forgot-password", methods=["POST"])
    def auth_forgot_password():
        data = request.get_json(silent=True) or {}
        ok, msg = request_password_reset(
            str(data.get("identifier", "")),
            request.url_root,
            None,
            request.remote_addr,
        )
        return jsonify({"success": ok, "message": msg}), (200 if ok else 503)

    @app.route("/api/auth/reset-password", methods=["POST"])
    def auth_reset_password():
        data = request.get_json(silent=True) or {}
        ok, msg = reset_password(str(data.get("token", "")), str(data.get("new_password", "")))
        return jsonify({"success": ok, "message": msg}), (200 if ok else 400)

    @app.route("/api/alerts", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer", "barista"])
    def alerts_list():
        return jsonify(get_alert_summary(g.current_user.get("branch_id")))

    @app.route("/api/alerts/<int:alert_id>/acknowledge", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer", "barista"])
    def alerts_acknowledge(alert_id):
        ok = acknowledge_alert(alert_id, g.current_user["id"], g.current_user.get("branch_id"))
        return jsonify({"success": ok}), (200 if ok else 404)

    @app.route("/api/auth/me", methods=["GET"])
    @require_auth()
    def auth_me():
        return jsonify(g.current_user)

    @app.route("/api/auth/profile", methods=["PUT"])
    @require_auth()
    def auth_update_own_profile():
        data = request.get_json(force=True) or {}
        success, msg = update_own_profile(g.current_user, data)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/developer/password", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def developer_change_password():
        data = request.get_json(silent=True) or {}
        success, msg = update_own_profile(g.current_user, {
            "current_password": data.get("current_password"),
            "new_password": data.get("new_password"),
        })
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/users/me/language", methods=["PUT"])
    @require_auth()
    def users_update_language():
        data = request.get_json(silent=True) or {}
        success, msg = update_own_language(g.current_user, data.get("language") or data.get("preferred_language"))
        return jsonify({"success": success, "message": msg, "preferred_language": data.get("language") or data.get("preferred_language")}), (200 if success else 400)

    @app.route("/api/users/me/preferences", methods=["PUT"])
    @require_auth()
    def users_update_preferences():
        data = request.get_json(silent=True) or {}
        success, msg = update_own_preferences(g.current_user, data)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    # --- User Management (Admin & Developer) ---
    @app.route("/api/users", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def users_list():
        return jsonify(list_users(g.current_user))

    @app.route("/api/users", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def users_create():
        data = request.get_json(force=True) or {}
        res, msg = create_user(g.current_user, data, request.remote_addr)
        if not res:
            return jsonify({"error": msg}), 400
        return jsonify({"user": res, "message": msg}), 201

    @app.route("/api/users/<int:user_id>", methods=["PUT"])
    @require_auth(allowed_roles=["admin", "developer"])
    def users_update(user_id):
        data = request.get_json(force=True) or {}
        success, msg = update_user(g.current_user, user_id, data, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/users/<int:user_id>", methods=["DELETE"])
    @require_auth(allowed_roles=["admin", "developer"])
    def users_delete(user_id):
        success, msg = delete_user(g.current_user, user_id, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/admin/mail-settings", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def admin_mail_settings():
        return jsonify(get_mail_settings())

    @app.route("/api/admin/mail-settings", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def admin_save_mail_settings():
        data = request.get_json(silent=True) or {}
        success, msg = save_mail_settings(data)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    # --- Products & Variants ---
    @app.route("/api/products", methods=["GET"])
    @require_auth()
    def products_list():
        active_only = request.args.get("active_only", "0") == "1"
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(list_products(branch_id=branch_id, active_only=active_only))

    @app.route("/api/products/reorder", methods=["POST"])
    @require_auth()
    def products_reorder():
        if g.current_user["role"] not in {"admin", "barista", "developer"}:
            return jsonify({"error": "Bu əməliyyat üçün icazəniz yoxdur."}), 403
        data = request.get_json(silent=True) or {}
        try:
            product_ids = [int(value) for value in data.get("product_ids", [])]
        except (TypeError, ValueError):
            return jsonify({"error": "Məhsul sırası düzgün deyil."}), 400
        success, message = reorder_products(
            product_ids, g.current_user.get("branch_id", 1)
        )
        return jsonify({"success": success, "message": message}), (200 if success else 400)

    @app.route("/api/products", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def products_create():
        data = request.get_json(force=True) or {}
        prod, msg = create_product(g.current_user, data, request.remote_addr)
        if not prod:
            return jsonify({"error": msg}), 400
        return jsonify({"product": prod, "message": msg}), 201

    @app.route("/api/products/<int:prod_id>", methods=["PUT"])
    @require_auth(allowed_roles=["admin", "developer"])
    def products_update(prod_id):
        data = request.get_json(force=True) or {}
        success, msg = update_product(g.current_user, prod_id, data, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/products/<int:prod_id>", methods=["DELETE"])
    @require_auth(allowed_roles=["admin", "developer"])
    def products_delete(prod_id):
        success, msg = delete_product(g.current_user, prod_id, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/products/<int:prod_id>/variants", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def products_add_variant(prod_id):
        data = request.get_json(force=True) or {}
        var, msg = add_product_variant(g.current_user, prod_id, data)
        if not var:
            return jsonify({"error": msg}), 400
        if not var:
            return jsonify({"error": msg}), 400
        return jsonify({"variant": var, "message": msg}), 201

    @app.route("/api/products/variants/<int:variant_id>", methods=["DELETE"])
    @require_auth(allowed_roles=["admin", "developer"])
    def products_delete_variant_route(variant_id):
        success, msg = delete_product_variant(g.current_user, variant_id, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    # --- Recipes (Admin & Developer) ---
    @app.route("/api/recipes/<int:variant_id>", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def recipes_get(variant_id):
        return jsonify(get_recipe_for_variant(variant_id))

    @app.route("/api/recipes/<int:variant_id>", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def recipes_set(variant_id):
        data = request.get_json(force=True) or {}
        ingredients = data.get("ingredients", [])
        success, msg = set_recipe_for_variant(g.current_user, variant_id, ingredients, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/recipes/<int:recipe_id>", methods=["DELETE"])
    @require_auth(allowed_roles=["admin", "developer"])
    def recipes_delete_ingredient_route(recipe_id):
        success, msg = delete_recipe_ingredient(g.current_user, recipe_id, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/recipes/variant/<int:variant_id>", methods=["DELETE"])
    @require_auth(allowed_roles=["admin", "developer"])
    def recipes_clear_variant_route(variant_id):
        success, msg = clear_variant_recipe(g.current_user, variant_id, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    # --- Raw Materials Stock (Admin & Developer) ---
    @app.route("/api/stock", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def stock_list():
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(list_raw_materials(branch_id=branch_id))

    @app.route("/api/reports/stock-depletion", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def stock_depletion_report():
        return jsonify(get_stock_depletion_overview(g.current_user.get("branch_id", 1)))

    @app.route("/api/stock", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def stock_create():
        data = request.get_json(force=True) or {}
        res, msg = create_raw_material(g.current_user, data, request.remote_addr)
        if not res:
            return jsonify({"error": msg}), 400
        return jsonify({"material": res, "message": msg}), 201

    @app.route("/api/stock/<int:mat_id>", methods=["PUT"])
    @require_auth(allowed_roles=["admin", "developer"])
    def stock_update(mat_id):
        data = request.get_json(force=True) or {}
        success, msg = update_raw_material(g.current_user, mat_id, data, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/stock/<int:mat_id>", methods=["DELETE"])
    @require_auth(allowed_roles=["admin", "developer"])
    def stock_delete(mat_id):
        success, msg = delete_raw_material(g.current_user, mat_id, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/stock/<int:mat_id>/restock", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def stock_restock(mat_id):
        data = request.get_json(force=True) or {}
        qty = float(data.get("quantity", 0.0))
        notes = data.get("notes", "")
        try:
            waste = float(data.get("waste_quantity", 0) or 0)
        except (TypeError, ValueError):
            return jsonify({"error": "İtki miqdarı düzgün deyil."}), 400
        success, msg = restock_raw_material(g.current_user, mat_id, qty, notes, request.remote_addr, waste)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    # --- Barista Orders & Sales ---
    @app.route("/api/orders", methods=["POST"])
    @require_auth()
    def orders_create():
        # Trial lock check
        lic = get_system_license_status()
        if lic.get("is_locked"):
            return jsonify({"error": f"Sistem bloklanıb: {lic.get('message')}"}), 403

        data = request.get_json(force=True) or {}
        res, msg = create_order(g.current_user, data, request.remote_addr)
        if not res:
            return jsonify({"error": msg}), 400

        # Incremental ML weight update on order
        train_or_update_ml_models()
        return jsonify(res), 201

    @app.route("/api/orders/recent", methods=["GET"])
    @require_auth()
    def orders_recent():
        branch_id = g.current_user.get("branch_id", 1)
        try:
            limit = max(1, min(200, int(request.args.get("limit", 50))))
        except (TypeError, ValueError):
            return jsonify({"error": "limit düzgün tam ədəd olmalıdır"}), 400
        return jsonify(list_recent_orders(branch_id, limit))

    @app.route("/api/cash-movements", methods=["GET", "POST"])
    @app.route("/api/cash_movements", methods=["GET", "POST"])
    @require_auth()
    def cash_movements_route():
        branch_id = g.current_user.get("branch_id", 1)
        if request.method == "POST":
            result, message = create_cash_movement(
                g.current_user, request.get_json(force=True) or {}, request.remote_addr
            )
            if not result:
                return jsonify({"error": message}), 400
            return jsonify({"movement": result, "message": message}), 201
        try:
            limit = max(1, min(1000, int(request.args.get("limit", 200))))
        except (TypeError, ValueError):
            return jsonify({"error": "limit düzgün tam ədəd olmalıdır"}), 400
        return jsonify(list_cash_movements(
            branch_id, request.args.get("start"), request.args.get("end"),
            request.args.get("shift_id"), limit
        ))

    @app.route("/api/orders/<int:order_id>/ticket", methods=["GET"])
    @require_auth()
    def orders_ticket(order_id):
        if g.current_user.get("role") != "developer":
            with get_db() as conn:
                order = conn.execute("SELECT branch_id FROM orders WHERE id = ?", (order_id,)).fetchone()
            if order and order["branch_id"] != g.current_user.get("branch_id", 1):
                return jsonify({"error": "Bu sifariş sizin filialınıza aid deyil."}), 403
        ticket = format_internal_ticket(order_id)
        if not ticket:
            return jsonify({"error": "Sifariş tapılmadı"}), 404
        return jsonify(ticket)

    @app.route("/api/orders/<int:order_id>/cancel", methods=["POST"])
    @require_auth()
    def orders_cancel(order_id):
        data = request.get_json(force=True) or {}
        reason = data.get("reason", "")
        success, msg = cancel_order(g.current_user, order_id, reason, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    # --- Barista Shortcuts ---
    @app.route("/api/shortcuts", methods=["GET"])
    @require_auth()
    def shortcuts_get():
        return jsonify(get_user_shortcuts(g.current_user["id"]))

    @app.route("/api/shortcuts", methods=["POST"])
    @require_auth()
    def shortcuts_set():
        data = request.get_json(force=True) or {}
        var_ids = data.get("variant_ids", [])
        success, msg = set_user_shortcuts(g.current_user["id"], var_ids)
        return jsonify({"success": success, "message": msg})

    @app.route("/api/shortcuts/add", methods=["POST"])
    @require_auth()
    def shortcuts_add():
        data = request.get_json(force=True) or {}
        variant_id = data.get("variant_id")
        custom_label = data.get("custom_label")
        icon_url = data.get("icon_url")
        if not variant_id:
            return jsonify({"error": "variant_id tələb olunur"}), 400
        success, msg, res = add_user_shortcut(g.current_user["id"], int(variant_id), custom_label, icon_url)
        if not success:
            return jsonify({"error": msg}), 400
        return jsonify({
            "success": True,
            "message": msg,
            "shortcut": res,
            "shortcut_id": res.get("shortcut_id") if res else None
        }), 201

    @app.route("/api/shortcuts/<int:shortcut_id>", methods=["PUT"])
    @require_auth()
    def shortcuts_update(shortcut_id):
        data = request.get_json(force=True) or {}
        custom_label = data.get("custom_label")
        icon_url = data.get("icon_url")
        success, msg = update_user_shortcut(g.current_user["id"], shortcut_id, custom_label, icon_url)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/shortcuts/<int:shortcut_id>", methods=["DELETE"])
    @require_auth()
    def shortcuts_delete(shortcut_id):
        success, msg = remove_user_shortcut(g.current_user["id"], shortcut_id)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/shortcuts/reorder", methods=["POST"])
    @require_auth()
    def shortcuts_reorder():
        data = request.get_json(force=True) or {}
        ids = data.get("shortcut_ids", [])
        success, msg = reorder_user_shortcuts(g.current_user["id"], ids)
        return jsonify({"success": success, "message": msg})

    @app.route("/api/icons/presets", methods=["GET"])
    @require_auth()
    def list_preset_icons():
        icons_dir = os.path.join(BASE_DIR, "app", "static", "images", "icons")
        presets = []
        if os.path.exists(icons_dir):
            for f in sorted(os.listdir(icons_dir)):
                if f.endswith(".svg"):
                    name = f.rsplit(".", 1)[0].replace("_", " ").title()
                    presets.append({"name": name, "url": f"/static/images/icons/{f}"})
        return jsonify(presets)

    @app.route("/api/upload", methods=["POST"])
    @require_auth()
    def file_upload():
        if "file" not in request.files:
            return jsonify({"error": "Fayl seçilməyib"}), 400
        file = request.files["file"]
        if not file or file.filename == "":
            return jsonify({"error": "Fayl adı boşdur"}), 400
        import uuid
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "svg"
        allowed = {"svg"}
        if ext not in allowed:
            return jsonify({"error": "Yalnız təhlükəsiz SVG ikon və loqolar dəstəklənir"}), 400
        upload_dir = os.path.join(BASE_DIR, "app", "static", "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        unique_name = f"up_{uuid.uuid4().hex[:12]}.svg"
        save_path = os.path.join(upload_dir, unique_name)
        try:
            content = file.stream.read(512 * 1024)
            lowered = content.lower()
            if any(
                marker in lowered
                for marker in (
                    b"<!doctype",
                    b"<!entity",
                    b"<script",
                    b"<foreignobject",
                    b"<iframe",
                    b"<object",
                    b"<embed",
                    b"javascript:",
                    b"data:text/html",
                    b"xlink:href",
                    b"href=",
                )
            ):
                return jsonify({"error": "SVG faylında təhlükəli məzmun aşkarlandı"}), 400
            if b"<svg" not in content[:2048].lower():
                return jsonify({"error": "Düzgün SVG faylı seçilməyib"}), 400
            root = ET.fromstring(content)
            for element in root.iter():
                tag = element.tag.rsplit("}", 1)[-1].lower() if isinstance(element.tag, str) else ""
                if tag in {"script", "foreignobject", "iframe", "object", "embed"}:
                    return jsonify({"error": "SVG faylında təhlükəli element aşkarlandı"}), 400
                if any(str(attr).lower().startswith("on") for attr in element.attrib):
                    return jsonify({"error": "SVG faylında hadisə atributu aşkarlandı"}), 400
            with open(save_path, "wb") as output:
                output.write(content)
            return jsonify({"url": f"/static/uploads/{unique_name}"}), 201
        except Exception as e:
            logger.error(f"Error processing upload: {e}")
            return jsonify({"error": "Şəkli emal etmək mümkün olmadı"}), 500

    # --- Shifts ---
    @app.route("/api/shifts/active", methods=["GET"])
    @require_auth()
    def shifts_active():
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(get_active_shift(branch_id) or {})

    @app.route("/api/shifts/open", methods=["POST"])
    @require_auth()
    def shifts_open():
        data = request.get_json(force=True) or {}
        try:
            opening_cash = float(data.get("opening_cash", 0.0))
        except (TypeError, ValueError):
            return jsonify({"error": "İlkin kassa məbləği düzgün deyil."}), 400
        notes = data.get("notes", "")
        res, msg = open_shift(g.current_user, opening_cash, notes, request.remote_addr)
        if not res:
            return jsonify({"error": msg}), 400
        return jsonify(res), 201

    @app.route("/api/shifts/<int:shift_id>/close", methods=["POST"])
    @require_auth()
    def shifts_close(shift_id):
        data = request.get_json(force=True) or {}
        try:
            closing_cash = float(data.get("closing_cash", 0.0))
        except (TypeError, ValueError):
            return jsonify({"error": "Yekun kassa məbləği düzgün deyil."}), 400
        notes = data.get("notes", "")
        res, msg = close_shift(g.current_user, shift_id, closing_cash, notes, request.remote_addr)
        if not res:
            return jsonify({"error": msg}), 400
        return jsonify(res)

    @app.route("/api/shifts", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def shifts_list():
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(list_shifts(branch_id))

    # --- Inventory Count Sessions ---
    @app.route("/api/inventory/start", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def inventory_start():
        data = request.get_json(force=True) or {}
        notes = data.get("notes", "")
        res, msg = start_inventory_session(g.current_user, notes, request.remote_addr)
        if not res:
            return jsonify({"error": msg}), 400
        return jsonify(res), 201

    @app.route("/api/inventory/<int:count_id>", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def inventory_get(count_id):
        session = get_inventory_session(count_id)
        if not session:
            return jsonify({"error": "Sessiya tapılmadı"}), 404
        if (
            g.current_user.get("role") != "developer"
            and session.get("branch_id") != g.current_user.get("branch_id", 1)
        ):
            return jsonify({"error": "Bu inventarizasiya sizin filialınıza aid deyil."}), 403
        return jsonify(session)

    @app.route("/api/inventory/<int:count_id>", methods=["PUT"])
    @require_auth(allowed_roles=["admin", "developer"])
    def inventory_update(count_id):
        data = request.get_json(force=True) or {}
        items = data.get("items", [])
        success, msg = update_inventory_counts(g.current_user, count_id, items)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/inventory/<int:count_id>/confirm", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def inventory_confirm(count_id):
        data = request.get_json(force=True) or {}
        notes = data.get("notes", "")
        success, msg = confirm_inventory_adjustments(g.current_user, count_id, notes, request.remote_addr)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/inventory", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def inventory_list():
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(list_inventory_sessions(branch_id))

    # --- Reports & Business Analytics (Admin & Developer) ---
    @app.route("/api/reports/overview", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def reports_overview():
        try:
            days = max(1, min(366, int(request.args.get("days", 7))))
        except (TypeError, ValueError):
            return jsonify({"error": "days düzgün tam ədəd olmalıdır"}), 400
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(get_sales_overview(branch_id, days))

    @app.route("/api/reports/daily", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def reports_daily():
        try:
            days = max(1, min(366, int(request.args.get("days", 14))))
        except (TypeError, ValueError):
            return jsonify({"error": "days düzgün tam ədəd olmalıdır"}), 400
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(get_daily_sales_chart(branch_id, days))

    @app.route("/api/reports/sales", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def reports_sales():
        try:
            report = get_sales_report(
                g.current_user.get("branch_id", 1),
                request.args.get("period", "daily"),
                request.args.get("date"),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(report)

    @app.route("/api/reports/end-of-day", methods=["GET"])
    @app.route("/api/reports/eod", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer", "barista"])
    def reports_end_of_day():
        try:
            report = get_end_of_day_report(
                g.current_user.get("branch_id", 1),
                preset=request.args.get("preset", request.args.get("date_preset", "today")),
                start=request.args.get("start", request.args.get("from")),
                end=request.args.get("end", request.args.get("to")),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(report)

    @app.route("/api/reports/hourly", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def reports_hourly():
        try:
            days = max(1, min(366, int(request.args.get("days", 30))))
        except (TypeError, ValueError):
            return jsonify({"error": "days düzgün tam ədəd olmalıdır"}), 400
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(get_hourly_sales_traffic(branch_id, days))

    @app.route("/api/reports/top-products", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def reports_top_products():
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(get_top_selling_products(branch_id))

    @app.route("/api/reports/baristas", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def reports_baristas():
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(get_barista_performance(branch_id))

    @app.route("/api/reports/employees/<int:employee_id>", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def reports_employee(employee_id):
        report = get_employee_report(g.current_user, employee_id)
        if not report:
            return jsonify({"error": "Bu işçi üçün hesabat əlçatan deyil."}), 404
        return jsonify(report)

    @app.route("/api/reports/depletion", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def reports_depletion():
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(get_stock_depletion_overview(branch_id))

    @app.route("/api/reports/export", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def reports_export():
        period = request.args.get("period", "daily").lower()
        fmt = request.args.get("format", "csv").lower()
        if period not in {"daily", "monthly", "yearly", "all"} or fmt not in {"csv", "json", "txt"}:
            return jsonify({"error": "Period və format düzgün deyil."}), 400
        content, mimetype, extension = build_sales_export(g.current_user.get("branch_id", 1), period, fmt)
        return Response(content, mimetype=mimetype, headers={"Content-Disposition": f"attachment; filename=illy_sales_{period}.{extension}"})

    # --- Machine Learning ---
    @app.route("/api/ml/recommendations", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def ml_recommendations():
        branch_id = g.current_user.get("branch_id", 1)
        return jsonify(generate_business_recommendations(branch_id))

    @app.route("/api/ml/metrics", methods=["GET"])
    @require_auth(allowed_roles=["developer"])
    def ml_metrics():
        return jsonify(get_developer_ml_metrics())

    # --- Retention Policy ---
    @app.route("/api/retention", methods=["GET"])
    @require_auth(allowed_roles=["admin", "developer"])
    def retention_get():
        return jsonify({"policy": get_current_retention_policy()})

    @app.route("/api/retention", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def retention_set():
        data = request.get_json(force=True) or {}
        policy = data.get("policy", "never")
        success, msg = set_retention_policy(policy)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/retention/run", methods=["POST"])
    @require_auth(allowed_roles=["admin", "developer"])
    def retention_run():
        res = execute_retention_cleanup()
        return jsonify(res)

    # --- Sync Configuration & Actions ---
    @app.route("/api/sync/config", methods=["GET"])
    @require_auth(allowed_roles=["developer"])
    def sync_config_get():
        return jsonify(get_sync_configuration())

    @app.route("/api/sync/config", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def sync_config_set():
        data = request.get_json(force=True) or {}
        mode = data.get("mode", "local_only")
        url = data.get("url", "")
        token = data.get("token", "")
        success, msg = update_sync_configuration(mode, url, token)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/sync/test", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def sync_test():
        data = request.get_json(force=True) or {}
        url = data.get("url", "")
        token = data.get("token", "")
        success, msg = test_remote_connection(url, token)
        return jsonify({"success": success, "message": msg}), (200 if success else 400)

    @app.route("/api/sync/now", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def sync_now():
        return jsonify(sync_pending_records())

    @app.route("/api/sync/all", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def sync_all():
        return jsonify(sync_all_existing_data_to_remote())

    @app.route("/api/sync/download-package", methods=["GET"])
    @require_auth(allowed_roles=["developer"])
    def sync_download_package():
        zip_bytes = generate_remote_code_zip()
        return send_file(
            BytesIO(zip_bytes),
            mimetype="application/zip",
            as_attachment=True,
            download_name="illy_coffee_remote_server.zip",
        )

    # --- Developer Diagnostics, Security & Exports ---
    @app.route("/api/developer/diagnostics", methods=["GET"])
    @require_auth(allowed_roles=["developer"])
    def developer_diagnostics():
        return jsonify(get_system_diagnostics())

    @app.route("/api/developer/branding", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def developer_branding():
        data = request.get_json(force=True) or {}
        success, msg = update_system_branding(data)
        return jsonify({"success": success, "message": msg})

    @app.route("/api/developer/encryption", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def developer_encryption():
        data = request.get_json(force=True) or {}
        enabled = bool(data.get("enabled", False))
        passphrase = str(data.get("passphrase", ""))
        success, msg = set_encryption_mode(enabled, passphrase)
        return jsonify({"success": success, "message": msg})

    @app.route("/api/developer/compression", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def developer_compression():
        data = request.get_json(force=True) or {}
        enabled = bool(data.get("enabled", False))
        success, msg = set_compression_mode(enabled)
        return jsonify({"success": success, "message": msg})

    @app.route("/api/backup", methods=["GET"])
    @require_auth(allowed_roles=["developer"])
    def backup_list():
        return jsonify({"backups": list_backups()})

    @app.route("/api/backup", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def backup_create():
        try:
            result = create_backup()
            return jsonify(result), 201
        except (OSError, sqlite3.Error, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/backup/integrity", methods=["GET"])
    @require_auth(allowed_roles=["developer"])
    def backup_integrity():
        return jsonify(check_integrity())

    @app.route("/api/backup/vacuum", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def backup_vacuum():
        return jsonify(vacuum_database())

    @app.route("/api/backup/restore", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def backup_restore():
        data = request.get_json(silent=True) or {}
        path = data.get("path")
        if not path:
            return jsonify({"error": "Backup path is required"}), 400
        try:
            requested = Path(str(path)).resolve()
            backup_root = BACKUP_DIR.resolve()
            if backup_root not in requested.parents:
                return jsonify({"error": "Only managed backup files can be restored."}), 400
            return jsonify(restore_backup(requested))
        except (OSError, ValueError, sqlite3.Error) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/developer/network-settings", methods=["GET", "PUT"])
    @require_auth(allowed_roles=["developer"])
    def developer_network_settings():
        if request.method == "GET":
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT key, value FROM system_settings WHERE key IN ('server_host', 'server_port')"
                ).fetchall()
            values = {row["key"]: row["value"] for row in rows}
            return jsonify({"host": values.get("server_host", "127.0.0.1"), "port": int(values.get("server_port", 8000))})
        data = request.get_json(silent=True) or {}
        host = str(data.get("host", "127.0.0.1")).strip()
        try:
            port = int(data.get("port", 8000))
        except (TypeError, ValueError):
            return jsonify({"error": "Port must be a number."}), 400
        if host not in {"127.0.0.1", "0.0.0.0", "localhost"}:
            return jsonify({"error": "Only localhost or all-interface binding is allowed."}), 400
        if not 1 <= port <= 65535:
            return jsonify({"error": "Port must be between 1 and 65535."}), 400
        with get_db() as conn:
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('server_host', ?, CURRENT_TIMESTAMP)", (host,))
            conn.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('server_port', ?, CURRENT_TIMESTAMP)", (str(port),))
        restart_scheduled = not app.testing and os.path.basename(sys.argv[0]) == "run.py"
        if restart_scheduled:
            def restart_process():
                os.execv(sys.executable, [sys.executable, *sys.argv])
            threading.Timer(0.35, restart_process).start()
        return jsonify({"success": True, "host": host, "port": port, "restart_required": True,
                        "restart_scheduled": restart_scheduled,
                        "message": "Network settings saved. The application will restart to apply the new binding."
                        if restart_scheduled else
                        "Network settings saved. Restart the application to apply the new binding."})

    @app.route("/api/developer/audit-logs", methods=["GET"])
    @require_auth(allowed_roles=["developer"])
    def developer_audit_logs():
        try:
            limit = max(1, min(200, int(request.args.get("limit", 50))))
        except (TypeError, ValueError):
            return jsonify({"error": "limit düzgün tam ədəd olmalıdır"}), 400
        return jsonify(list_developer_audit_logs(limit))

    @app.route("/api/developer/generate-key", methods=["POST"])
    @require_auth(allowed_roles=["developer"])
    def developer_generate_key():
        data = request.get_json(force=True) or {}
        branch_code = data.get("branch_code", "ILLY-BAKU-01")
        key = generate_activation_key(branch_code)
        return jsonify({"branch_code": branch_code, "activation_key": key})

    @app.route("/api/developer/export/sql", methods=["GET"])
    @require_auth(allowed_roles=["developer"])
    def developer_export_sql():
        sql_content, msg = export_db_sql()
        if not sql_content:
            return jsonify({"error": msg}), 403
        return Response(
            sql_content,
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment; filename=coffeeshop_export.sql"},
        )

    @app.route("/api/developer/export/json", methods=["GET"])
    @require_auth(allowed_roles=["developer"])
    def developer_export_json():
        json_content, msg = export_db_json()
        if not json_content:
            return jsonify({"error": msg}), 403
        return Response(
            json_content,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=coffeeshop_export.json"},
        )

    @app.route("/api/developer/export/txt", methods=["GET"])
    @require_auth(allowed_roles=["developer"])
    def developer_export_txt():
        txt_content, msg = export_db_tree_txt()
        if not txt_content:
            return jsonify({"error": msg}), 403
        return Response(
            txt_content,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=coffeeshop_tree_structure.txt"},
        )

    return app
