"""
Database Core Module
Handles SQLite connection management, WAL mode, migrations, and bootstrapping.
"""
import sqlite3
import datetime
import json
import logging
import time
from contextlib import contextmanager
from app.core.config import (
    DB_PATH,
    DEFAULT_BRANCH_ID,
    DEFAULT_BRANCH_NAME,
    DEFAULT_BRANCH_CODE,
    DEVELOPER_USERNAME,
    DEVELOPER_CODE_PASSWORD,
    DEVELOPER_PASSWORD_WAS_GENERATED,
    RETENTION_POLICIES,
)
import bcrypt

logger = logging.getLogger(__name__)

def dict_from_row(row):
    """Convert sqlite3.Row to python dict."""
    if row is None:
        return None
    return dict(row)

def get_connection(db_file=None):
    """Create and configure a connection to the SQLite database."""
    target_path = str(db_file or DB_PATH)
    conn = sqlite3.connect(target_path, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    # Configure WAL mode and foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    return conn

@contextmanager
def get_db(db_file=None):
    """Context manager for database connections with auto-commit/rollback."""
    conn = get_connection(db_file)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db(db_file=None):
    """Initialize all database tables and seed bootstrap Developer."""
    with get_db(db_file) as conn:
        cursor = conn.cursor()

        # Schema Migrations tracking
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 1. Branches table (Multi-branch readiness)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            code TEXT UNIQUE NOT NULL,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2. Users table (Developer, Admin, Barista)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER REFERENCES branches(id) ON DELETE SET NULL,
            username TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('developer', 'admin', 'barista')),
            password_hash TEXT NOT NULL,
            token_version INTEGER NOT NULL DEFAULT 0,
            email TEXT,
            avatar_url TEXT,
            avatar_color TEXT,
            avatar_theme TEXT NOT NULL DEFAULT 'plain',
            preferred_language TEXT NOT NULL DEFAULT 'az',
            preferred_theme TEXT NOT NULL DEFAULT 'soft-dark',
            preferred_font_size TEXT NOT NULL DEFAULT 'normal',
            last_activity_at TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            employment_end_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT;")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0;")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN receipt_signature TEXT;")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN employment_end_at TIMESTAMP;")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN preferred_language TEXT NOT NULL DEFAULT 'az';")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN preferred_theme TEXT NOT NULL DEFAULT 'soft-dark';")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN preferred_font_size TEXT NOT NULL DEFAULT 'normal';")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN last_activity_at TIMESTAMP;")
        except sqlite3.OperationalError:
            pass
        cursor.execute("UPDATE users SET preferred_theme = 'soft-dark' WHERE preferred_theme IS NULL OR preferred_theme = 'light'")
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN avatar_color TEXT;")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN avatar_theme TEXT NOT NULL DEFAULT 'plain';")
        except sqlite3.OperationalError:
            pass
        from app.core.avatar import avatar_color_for_user, build_avatar_url
        user_rows = cursor.execute("SELECT id, avatar_color, avatar_theme FROM users").fetchall()
        for user_row in user_rows:
            color = user_row["avatar_color"] or avatar_color_for_user(user_row["id"])
            theme = user_row["avatar_theme"] or "plain"
            cursor.execute(
                "UPDATE users SET avatar_color = ?, avatar_theme = ?, avatar_url = ? WHERE id = ?",
                (color, theme, build_avatar_url(color, theme), user_row["id"]),
            )
        cursor.execute("UPDATE users SET preferred_language = 'az' WHERE preferred_language IS NULL OR preferred_language = ''")
        cursor.execute("UPDATE users SET preferred_font_size = 'normal' WHERE preferred_font_size IS NULL OR preferred_font_size NOT IN ('small', 'normal', 'large')")

        # 3. User shortcuts (Barista pinned products with custom icons & labels)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_shortcuts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            variant_id INTEGER NOT NULL,
            custom_label TEXT,
            icon_url TEXT,
            sort_order INTEGER DEFAULT 0,
            UNIQUE(user_id, variant_id)
        );
        """)

        # Safe migration for existing databases
        try:
            cursor.execute("ALTER TABLE user_shortcuts ADD COLUMN custom_label TEXT;")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE user_shortcuts ADD COLUMN icon_url TEXT;")
        except Exception:
            pass

        # 4. Products table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER REFERENCES branches(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            image_url TEXT,
            sort_order INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 5. Product Variants table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            price REAL NOT NULL CHECK(price >= 0),
            sku TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 6. Raw Materials table (The main stock truth)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER REFERENCES branches(id) ON DELETE SET NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            unit TEXT NOT NULL,
            current_stock REAL DEFAULT 0,
            minimum_alert_threshold REAL DEFAULT 0,
            cost_per_unit REAL DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 7. Recipes table (Flexible multi-ingredient per variant)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            variant_id INTEGER NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
            raw_material_id INTEGER NOT NULL REFERENCES raw_materials(id) ON DELETE RESTRICT,
            quantity REAL NOT NULL CHECK(quantity > 0),
            waste_factor REAL NOT NULL DEFAULT 1.0 CHECK(waste_factor >= 1.0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(variant_id, raw_material_id)
        );
        """)
        try:
            cursor.execute("ALTER TABLE recipes ADD COLUMN waste_factor REAL NOT NULL DEFAULT 1.0;")
        except sqlite3.OperationalError:
            pass

        # 8. Stock Transactions Ledger
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER REFERENCES branches(id),
            raw_material_id INTEGER NOT NULL REFERENCES raw_materials(id),
            change_amount REAL NOT NULL,
            balance_after REAL NOT NULL,
            reference_type TEXT NOT NULL CHECK(reference_type IN ('order', 'order_cancel', 'inventory_adjustment', 'restock', 'spillage_waste')),
            reference_id INTEGER,
            notes TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 9. Shifts table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS shifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER REFERENCES branches(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            opened_at TIMESTAMP NOT NULL,
            closed_at TIMESTAMP,
            opening_cash REAL DEFAULT 0,
            closing_cash REAL DEFAULT 0,
            expected_cash REAL DEFAULT 0,
            notes TEXT,
            status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 10. Orders table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER REFERENCES branches(id),
            shift_id INTEGER REFERENCES shifts(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            order_number TEXT UNIQUE NOT NULL,
            total_amount REAL NOT NULL,
            discount_type TEXT DEFAULT 'none' CHECK(discount_type IN ('none', 'percent', 'fixed', 'complementary')),
            discount_value REAL DEFAULT 0,
            discount_reason TEXT,
            is_complementary INTEGER DEFAULT 0,
            final_amount REAL NOT NULL,
            payment_method TEXT NOT NULL CHECK(payment_method IN ('cash', 'card', 'mixed', 'other')),
            fulfillment_type TEXT NOT NULL DEFAULT 'in_store',
            delivery_channel TEXT NOT NULL DEFAULT 'in_store',
            customer_type TEXT NOT NULL DEFAULT 'guest',
            status TEXT DEFAULT 'completed' CHECK(status IN ('completed', 'cancelled')),
            cancel_reason TEXT,
            cancelled_by INTEGER REFERENCES users(id),
            cancelled_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # Safe migrations for databases created before fulfillment channels
        # were introduced.  Existing orders remain in-store orders.
        for column_sql in (
            "ALTER TABLE orders ADD COLUMN fulfillment_type TEXT NOT NULL DEFAULT 'in_store'",
            "ALTER TABLE orders ADD COLUMN delivery_channel TEXT NOT NULL DEFAULT 'in_store'",
            "ALTER TABLE orders ADD COLUMN customer_type TEXT NOT NULL DEFAULT 'guest'",
        ):
            try:
                cursor.execute(column_sql)
            except sqlite3.OperationalError:
                pass

        # 11. Order Items table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            variant_id INTEGER REFERENCES product_variants(id),
            product_name TEXT NOT NULL,
            variant_name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL,
            subtotal REAL NOT NULL,
            notes TEXT
        );
        """)

        # 12. Inventory Counts Master
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER REFERENCES branches(id),
            user_id INTEGER NOT NULL REFERENCES users(id),
            status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'confirmed')),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TIMESTAMP
        );
        """)

        # 13. Inventory Count Items
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_count_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            count_id INTEGER NOT NULL REFERENCES inventory_counts(id) ON DELETE CASCADE,
            raw_material_id INTEGER NOT NULL REFERENCES raw_materials(id),
            system_quantity REAL NOT NULL,
            counted_quantity REAL NOT NULL,
            variance REAL NOT NULL,
            notes TEXT
        );
        """)

        # 14. Audit Logs (Business actions of Admin and Barista)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER,
            user_id INTEGER,
            username TEXT,
            role TEXT,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 15. Developer Audit Logs (Deep technical operations)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS developer_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Till/cash ledger.  This is deliberately separate from orders so
        # operational cash movements can never inflate sales revenue.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cash_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER REFERENCES branches(id) ON DELETE SET NULL,
            shift_id INTEGER REFERENCES shifts(id) ON DELETE SET NULL,
            user_id INTEGER NOT NULL REFERENCES users(id),
            direction TEXT NOT NULL CHECK(direction IN ('in', 'out')),
            amount REAL NOT NULL CHECK(amount > 0),
            is_debt INTEGER NOT NULL DEFAULT 0 CHECK(is_debt IN (0, 1)),
            related_debt TEXT,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        for column_sql in (
            "ALTER TABLE cash_movements ADD COLUMN reason TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE cash_movements ADD COLUMN is_debt_payment INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE cash_movements ADD COLUMN related_debt_id INTEGER",
        ):
            try:
                cursor.execute(column_sql)
            except sqlite3.OperationalError:
                pass
        try:
            cursor.execute("ALTER TABLE shifts ADD COLUMN cash_difference REAL NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE stock_transactions ADD COLUMN waste_quantity REAL NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        # 16. System Settings
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 17. ML Models and Weights Store (Strictly preserved across retention)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ml_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT UNIQUE NOT NULL,
            version TEXT NOT NULL,
            weights_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 18. Sync Queue (Offline-first incremental sync engine)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('insert', 'update', 'delete')),
            payload_json TEXT NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'synced', 'failed')),
            attempts INTEGER DEFAULT 0,
            last_error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            synced_at TIMESTAMP
        );
        """)

        # 19. Sync Conflicts Log
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sync_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,
            conflict_details TEXT NOT NULL,
            resolution_applied TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            requested_by INTEGER REFERENCES users(id),
            requested_ip TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER REFERENCES branches(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'warning',
            message TEXT NOT NULL,
            entity_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            resolved_by INTEGER REFERENCES users(id)
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts(resolved_at, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_tokens_hash ON password_reset_tokens(token_hash);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_tokens_expiry ON password_reset_tokens(expires_at);")

        # Indexes for fast search and high-speed POS lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_fulfillment ON orders(delivery_channel);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cash_movements_shift ON cash_movements(shift_id, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cash_movements_branch ON cash_movements(branch_id, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stock_tx_mat ON stock_transactions(raw_material_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON sync_queue(status);")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rate_limit_events (
            key TEXT PRIMARY KEY,
            window_started INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Bootstrap: Ensure default branch exists
        cursor.execute("SELECT id FROM branches WHERE id = ?", (DEFAULT_BRANCH_ID,))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO branches (id, name, code, address) VALUES (?, ?, ?, ?)",
                (DEFAULT_BRANCH_ID, DEFAULT_BRANCH_NAME, DEFAULT_BRANCH_CODE, "Nizami küç. 42, Bakı"),
            )

        # Bootstrap Rule C1: System starts with Developer only
        cursor.execute("SELECT id FROM users WHERE username = ?", (DEVELOPER_USERNAME,))
        dev_row = cursor.fetchone()
        if not dev_row:
            hashed_pw = bcrypt.hashpw(DEVELOPER_CODE_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            cursor.execute(
                """
                INSERT INTO users (branch_id, username, full_name, role, password_hash, avatar_url, avatar_color, avatar_theme, is_active)
                VALUES (?, ?, ?, 'developer', ?, ?, '#2563eb', 'plain', 1)
                """,
                (DEFAULT_BRANCH_ID, DEVELOPER_USERNAME, "Sistem Developer", hashed_pw, "/static/images/avatar-user.svg"),
            )
        else:
            # Keep the bootstrap identity represented by the users table and
            # prevent legacy databases from treating it as ordinary staff.
            cursor.execute(
                "UPDATE users SET role = 'developer', is_active = 1 WHERE username = ?",
                (DEVELOPER_USERNAME,),
            )
            if DEVELOPER_PASSWORD_WAS_GENERATED:
                hashed_pw = bcrypt.hashpw(DEVELOPER_CODE_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                cursor.execute(
                    "UPDATE users SET password_hash = ?, token_version = token_version + 1 WHERE username = ?",
                    (hashed_pw, DEVELOPER_USERNAME),
                )

        # Bootstrap default system settings
        default_settings = {
            "trial_start_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "is_real_mode": "0",
            "activation_key": "",
            "setup_completed": "0",
            "encryption_enabled": "0",
            "compression_enabled": "0",
            "retention_policy": "never",
            "remote_sync_mode": "local_only",
            "remote_sync_url": "",
            "remote_sync_token": "",
            "last_sync_timestamp": "",
            "shop_name": "Illy Specialty Coffee",
            "shop_tagline": "Authentic Italian Espresso Bar",
            "accent_color": "#c8102e",
            "logo_url": "/static/images/illy-logo.svg",
        }

        for key, val in default_settings.items():
            cursor.execute(
                "INSERT OR IGNORE INTO system_settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (key, val),
            )

        # Bootstrap initial ML Model state
        default_ml_weights = json.dumps({
            "alpha_smoothing": 0.35,
            "weekend_boost_factor": 1.25,
            "lead_time_days": 2.0,
            "safety_buffer_ratio": 1.20,
            "loss_history": [0.42, 0.35, 0.28, 0.22, 0.18],
            "epochs_completed": 12,
            "mean_absolute_error": 0.184,
        })
        default_ml_metrics = json.dumps({
            "accuracy_score": 91.6,
            "learning_quality": "Optimal",
        })
        cursor.execute(
            """
            INSERT OR IGNORE INTO ml_models (model_name, version, weights_json, metrics_json)
            VALUES ('coffee_depletion_predictor', 'v1.2.0', ?, ?)
            """,
            (default_ml_weights, default_ml_metrics),
        )

        # Record migration
        cursor.execute("INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (1, 'initial_schema')")
        cursor.execute("INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (2, 'security_rate_limits_and_bootstrap')")
        cursor.execute("INSERT OR IGNORE INTO schema_migrations (version, name) VALUES (3, 'cash_movements_and_order_fulfillment')")

    logger.info("Database initialized successfully.")

def consume_rate_limit(key: str, limit: int, window_seconds: int, db_file=None) -> tuple[bool, int]:
    """Atomically consume a persistent fixed-window rate-limit slot."""
    now = int(time.time())
    with get_db(db_file) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT window_started, attempts FROM rate_limit_events WHERE key = ?", (key,)
        ).fetchone()
        if not row or now - int(row["window_started"]) >= window_seconds:
            conn.execute(
                "INSERT OR REPLACE INTO rate_limit_events (key, window_started, attempts, updated_at) VALUES (?, ?, 1, CURRENT_TIMESTAMP)",
                (key, now),
            )
            return True, window_seconds
        attempts = int(row["attempts"])
        if attempts >= limit:
            return False, max(1, window_seconds - (now - int(row["window_started"])))
        conn.execute(
            "UPDATE rate_limit_events SET attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
            (key,),
        )
        return True, max(1, window_seconds - (now - int(row["window_started"])))
