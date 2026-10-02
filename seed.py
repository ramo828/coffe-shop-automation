"""
Database Seeding Script
Populates realistic Illy Specialty Coffee shop master data:
Raw materials, recipes, variants, users, shifts, and sample orders.
"""
import datetime
import bcrypt
from app.core.config import DEVELOPER_USERNAME, DEVELOPER_CODE_PASSWORD, DEFAULT_BRANCH_ID
from app.core.database import init_db, get_db
from app.core.avatar import avatar_color_for_user, build_avatar_url

def seed_database():
    print("Initializing schema...")
    init_db()

    with get_db() as conn:
        cursor = conn.cursor()

        # Reset setup/license state so every seed is deterministic.
        cursor.execute("DELETE FROM system_settings WHERE key IN ('setup_completed', 'is_real_mode', 'activation_key', 'trial_start_date', 'shop_name', 'shop_tagline', 'logo_url', 'banner_url', 'accent_color')")
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('trial_start_date', datetime('now'), CURRENT_TIMESTAMP)")
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('is_real_mode', '0', CURRENT_TIMESTAMP)")
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('activation_key', '', CURRENT_TIMESTAMP)")
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('setup_completed', '0', CURRENT_TIMESTAMP)")
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('shop_name', 'Illy Specialty Coffee', CURRENT_TIMESTAMP)")
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('shop_tagline', 'Authentic Italian Espresso Bar', CURRENT_TIMESTAMP)")
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('logo_url', '/static/images/illy-logo.svg', CURRENT_TIMESTAMP)")
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('banner_url', '', CURRENT_TIMESTAMP)")
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, updated_at) VALUES ('accent_color', '#c8102e', CURRENT_TIMESTAMP)")

        # 1. Staff Accounts (Admin & Baristas)
        print("Seeding staff accounts...")
        staff_data = [
            ("admin", "Leyla Əliyeva", "admin", "admin123!", "/static/avatars/admin_1.png"),
            ("barista_elvin", "Elvin Məmmədov", "barista", "barista123!", "/static/avatars/barista_1.png"),
            ("barista_nigar", "Nigar Qasımova", "barista", "barista123!", "/static/avatars/barista_2.png"),
        ]

        user_ids = {}
        for username, full_name, role, plain_pw, avatar in staff_data:
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            existing = cursor.fetchone()
            if not existing:
                pw_hash = bcrypt.hashpw(plain_pw.encode("utf-8"), bcrypt.gensalt(10)).decode("utf-8")
                cursor.execute(
                    """
                    INSERT INTO users (branch_id, username, full_name, role, password_hash, avatar_url, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (DEFAULT_BRANCH_ID, username, full_name, role, pw_hash, avatar),
                )
                user_ids[username] = cursor.lastrowid
            else:
                user_ids[username] = existing["id"]
            user_id = user_ids[username]
            color = avatar_color_for_user(user_id)
            cursor.execute(
                "UPDATE users SET avatar_color = ?, avatar_theme = COALESCE(avatar_theme, 'plain'), avatar_url = ?, last_activity_at = NULL WHERE id = ?",
                (color, build_avatar_url(color, "plain"), user_id),
            )
        cursor.execute("UPDATE users SET last_activity_at = NULL WHERE username = 'developer'")

        # 2. Raw Materials (The Stock Truth)
        print("Seeding raw materials...")
        raw_materials_data = [
            ("Illy Espresso Dənələri (Classico)", "Qəhvə Dənələri", "g", 15000.0, 3000.0, 0.045),
            ("Illy Espresso Dənələri (Intenso)", "Qəhvə Dənələri", "g", 10000.0, 2000.0, 0.045),
            ("Tam Yağlı Təbii Süd (3.2%)", "Süd və Alternativlər", "ml", 45000.0, 10000.0, 0.003),
            ("Yulaf Südü (Oat Milk)", "Süd və Alternativlər", "ml", 12000.0, 3000.0, 0.006),
            ("Badam Südü (Almond Milk)", "Süd və Alternativlər", "ml", 8000.0, 2000.0, 0.007),
            ("Vanil Siropu (Monin)", "Sirop və Dadlandırıcılar", "ml", 2500.0, 500.0, 0.025),
            ("Karamel Siropu (Monin)", "Sirop və Dadlandırıcılar", "ml", 2000.0, 500.0, 0.025),
            ("Fındıq Siropu (Monin)", "Sirop və Dadlandırıcılar", "ml", 1500.0, 400.0, 0.025),
            ("Kiçik Kağız Stəkan (8oz / 240ml)", "Qablaşdırma", "ədəd", 400.0, 100.0, 0.12),
            ("Böyük Kağız Stəkan (12oz / 350ml)", "Qablaşdırma", "ədəd", 500.0, 120.0, 0.15),
            ("Kiçik Stəkan Qapağı", "Qablaşdırma", "ədəd", 420.0, 100.0, 0.05),
            ("Böyük Stəkan Qapağı", "Qablaşdırma", "ədəd", 530.0, 120.0, 0.06),
            ("Şəkər & Taxta Qarışdırıcı Dəsti", "Qablaşdırma", "dəst", 800.0, 200.0, 0.03),
            ("Qazsız Su (İlly Aqua 0.5L)", "Digər İçkilər", "ədəd", 60.0, 15.0, 0.80),
            ("Klassik Kərə Yağlı Kruasan", "Şirniyyat", "ədəd", 30.0, 8.0, 1.50),
        ]

        material_ids = {}
        for name, category, unit, stock, min_alert, cost in raw_materials_data:
            cursor.execute("SELECT id FROM raw_materials WHERE name = ?", (name,))
            mat_row = cursor.fetchone()
            if not mat_row:
                cursor.execute(
                    """
                    INSERT INTO raw_materials (branch_id, name, category, unit, current_stock, minimum_alert_threshold, cost_per_unit, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (DEFAULT_BRANCH_ID, name, category, unit, stock, min_alert, cost),
                )
                material_ids[name] = cursor.lastrowid
            else:
                cursor.execute(
                    """
                    UPDATE raw_materials
                    SET branch_id = ?, category = ?, unit = ?, current_stock = ?, minimum_alert_threshold = ?, cost_per_unit = ?, is_active = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (DEFAULT_BRANCH_ID, category, unit, stock, min_alert, cost, mat_row["id"]),
                )
                material_ids[name] = mat_row["id"]

        # 3. Products, Variants and Recipes
        print("Seeding products, variants and flexible recipes...")
        catalog = [
            {
                "name": "Espresso Illy",
                "category": "Espresso",
                "description": "Əsl İtalyan üslublu klassik zəngin tək və ya cüt espresso.",
                "sort_order": 1,
                "variants": [
                    {
                        "name": "Tək (Single)",
                        "price": 3.50,
                        "recipe": [("Illy Espresso Dənələri (Classico)", 10.0)],
                    },
                    {
                        "name": "Cüt (Doppio)",
                        "price": 4.80,
                        "recipe": [("Illy Espresso Dənələri (Classico)", 18.0)],
                    },
                ]
            },
            {
                "name": "Cappuccino",
                "category": "Südlü Qəhvələr",
                "description": "Bərabər nisbətdə espresso, qaynar süd və ipək kimi sıx südlü köpük.",
                "sort_order": 2,
                "variants": [
                    {
                        "name": "Fincan (Ceramic Cup)",
                        "price": 5.50,
                        "recipe": [
                            ("Illy Espresso Dənələri (Classico)", 18.0),
                            ("Tam Yağlı Təbii Süd (3.2%)", 150.0),
                        ],
                    },
                    {
                        "name": "Böyük Takeaway",
                        "price": 6.80,
                        "recipe": [
                            ("Illy Espresso Dənələri (Classico)", 22.0),
                            ("Tam Yağlı Təbii Süd (3.2%)", 220.0),
                            ("Böyük Kağız Stəkan (12oz / 350ml)", 1.0),
                            ("Böyük Stəkan Qapağı", 1.0),
                        ],
                    },
                ]
            },
            {
                "name": "Caffè Latte",
                "category": "Südlü Qəhvələr",
                "description": "Zərif espresso və bol qaymaqlı buxarlanmış süd harmoniyası.",
                "sort_order": 3,
                "variants": [
                    {
                        "name": "Kiçik Takeaway",
                        "price": 5.50,
                        "recipe": [
                            ("Illy Espresso Dənələri (Classico)", 18.0),
                            ("Tam Yağlı Təbii Süd (3.2%)", 180.0),
                            ("Kiçik Kağız Stəkan (8oz / 240ml)", 1.0),
                            ("Kiçik Stəkan Qapağı", 1.0),
                        ],
                    },
                    {
                        "name": "Böyük Takeaway",
                        "price": 7.00,
                        "recipe": [
                            ("Illy Espresso Dənələri (Classico)", 22.0),
                            ("Tam Yağlı Təbii Süd (3.2%)", 260.0),
                            ("Böyük Kağız Stəkan (12oz / 350ml)", 1.0),
                            ("Böyük Stəkan Qapağı", 1.0),
                        ],
                    },
                ]
            },
            {
                "name": "Flat White",
                "category": "Südlü Qəhvələr",
                "description": "Güclü ikiqat ristretto və mikro-köpüklü incə süd təbəqəsi.",
                "sort_order": 4,
                "variants": [
                    {
                        "name": "Standart",
                        "price": 6.00,
                        "recipe": [
                            ("Illy Espresso Dənələri (Intenso)", 20.0),
                            ("Tam Yağlı Təbii Süd (3.2%)", 160.0),
                            ("Kiçik Kağız Stəkan (8oz / 240ml)", 1.0),
                            ("Kiçik Stəkan Qapağı", 1.0),
                        ],
                    },
                ]
            },
            {
                "name": "Americano",
                "category": "Espresso",
                "description": "Klassik espresso və isti su qarışığı, təmiz və balanslı dad.",
                "sort_order": 5,
                "variants": [
                    {
                        "name": "Kiçik (Small)",
                        "price": 4.20,
                        "recipe": [
                            ("Illy Espresso Dənələri (Classico)", 18.0),
                            ("Kiçik Kağız Stəkan (8oz / 240ml)", 1.0),
                            ("Kiçik Stəkan Qapağı", 1.0),
                        ],
                    },
                    {
                        "name": "Böyük (Large)",
                        "price": 5.20,
                        "recipe": [
                            ("Illy Espresso Dənələri (Classico)", 22.0),
                            ("Böyük Kağız Stəkan (12oz / 350ml)", 1.0),
                            ("Böyük Stəkan Qapağı", 1.0),
                        ],
                    },
                ]
            },
            {
                "name": "Caramel Macchiato",
                "category": "Xüsusi İçkilər",
                "description": "Vanilli buxar südü üzərinə espresso təbəqəsi və zəngin karamel siropu.",
                "sort_order": 6,
                "variants": [
                    {
                        "name": "Böyük Takeaway",
                        "price": 7.80,
                        "recipe": [
                            ("Illy Espresso Dənələri (Classico)", 22.0),
                            ("Tam Yağlı Təbii Süd (3.2%)", 240.0),
                            ("Karamel Siropu (Monin)", 20.0),
                            ("Böyük Kağız Stəkan (12oz / 350ml)", 1.0),
                            ("Böyük Stəkan Qapağı", 1.0),
                        ],
                    },
                ]
            },
            {
                "name": "Fransız Kruasanı",
                "category": "Şirniyyat",
                "description": "Əsl kərə yağı ilə bişirilmiş xırtıldayan təbii kruasan.",
                "sort_order": 7,
                "variants": [
                    {
                        "name": "1 ədəd",
                        "price": 4.50,
                        "recipe": [
                            ("Klassik Kərə Yağlı Kruasan", 1.0),
                            ("Şəkər & Taxta Qarışdırıcı Dəsti", 1.0),
                        ],
                    },
                ]
            },
        ]

        # Map default icons
        product_icon_map = {
            "Espresso Illy": "/static/images/icons/espresso.png",
            "Cappuccino": "/static/images/icons/cappuccino.png",
            "Caffè Latte": "/static/images/icons/latte.png",
            "Flat White": "/static/images/icons/cappuccino.png",
            "Americano": "/static/images/icons/americano.png",
            "Caramel Macchiato": "/static/images/icons/frappe.png",
            "Fransız Kruasanı": "/static/images/icons/croissant.png",
        }

        variant_ids = []
        variant_info_list = []
        for p in catalog:
            img_url = product_icon_map.get(p["name"], "/static/images/icons/default.png")
            cursor.execute("SELECT id FROM products WHERE name = ?", (p["name"],))
            p_row = cursor.fetchone()
            if not p_row:
                cursor.execute(
                    """
                    INSERT INTO products (branch_id, name, category, description, image_url, sort_order, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (DEFAULT_BRANCH_ID, p["name"], p["category"], p["description"], img_url, p["sort_order"]),
                )
                prod_id = cursor.lastrowid
            else:
                prod_id = p_row["id"]
                cursor.execute("UPDATE products SET image_url = ? WHERE id = ?", (img_url, prod_id))

            for v in p["variants"]:
                cursor.execute("SELECT id FROM product_variants WHERE product_id = ? AND name = ?", (prod_id, v["name"]))
                v_row = cursor.fetchone()
                if not v_row:
                    sku = f"SKU-{prod_id}-{v['name'][:3].upper()}"
                    cursor.execute(
                        """
                        INSERT INTO product_variants (product_id, name, price, sku, is_active)
                        VALUES (?, ?, ?, ?, 1)
                        """,
                        (prod_id, v["name"], v["price"], sku),
                    )
                    v_id = cursor.lastrowid
                else:
                    v_id = v_row["id"]
                variant_ids.append(v_id)
                variant_info_list.append({"id": v_id, "prod_name": p["name"], "var_name": v["name"], "img_url": img_url})

                # Set Recipe ingredients
                cursor.execute("DELETE FROM recipes WHERE variant_id = ?", (v_id,))
                for mat_name, qty in v["recipe"]:
                    m_id = material_ids.get(mat_name)
                    if m_id:
                        cursor.execute(
                            "INSERT INTO recipes (variant_id, raw_material_id, quantity) VALUES (?, ?, ?)",
                            (v_id, m_id, qty),
                        )

        # 4. Barista Shortcuts: Pin Cappuccino, Latte, Americano for Elvin and Nigar
        print("Setting default barista shortcuts with custom icons...")
        elvin_id = user_ids.get("barista_elvin")
        if elvin_id and variant_info_list:
            cursor.execute("DELETE FROM user_shortcuts WHERE user_id = ?", (elvin_id,))
            for idx, item in enumerate(variant_info_list[:6]):
                lbl = f"{item['prod_name']} ({item['var_name']})"
                cursor.execute(
                    """
                    INSERT INTO user_shortcuts (user_id, variant_id, custom_label, icon_url, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (elvin_id, item["id"], lbl, item["img_url"], idx),
                )

        # 5. Open a sample active shift for Barista Elvin
        print("Opening active shift...")
        cursor.execute("SELECT id FROM shifts WHERE status = 'open'")
        if not cursor.fetchone() and elvin_id:
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute(
                """
                INSERT INTO shifts (branch_id, user_id, opened_at, opening_cash, notes, status)
                VALUES (?, ?, ?, 100.0, 'Səhər növbəsi açıldı', 'open')
                """,
                (DEFAULT_BRANCH_ID, elvin_id, now_iso),
            )

    print("Database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
