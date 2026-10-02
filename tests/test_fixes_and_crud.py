"""
Comprehensive Tests for Recent Fixes and CRUD Endpoints:
1. Product & Variant CRUD (Create product, Delete variant, Delete product)
2. Stock CRUD (Update raw material, stock balance adjustment, Delete raw material)
3. Recipe Deletions (Delete ingredient, Clear variant recipe)
4. User Shortcuts (Add, Update, Reorder, Remove)
5. Profile Update Security (Mandatory current_password check via bcrypt)
6. Authenticated Developer Downloads (SQL, JSON, TXT exports & Remote ZIP package via header & ?token=)
"""
import unittest
import json
import io
import zipfile
from app.main import create_app
from app.core.database import get_db, init_db
from app.auth.auth import create_access_token
from app.security.license import activate_real_mode, generate_activation_key
from app.core.config import DEFAULT_BRANCH_CODE
from seed import seed_database

class TestFixesAndCrud(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        # Ensure REAL mode is active for export testing
        key = generate_activation_key(DEFAULT_BRANCH_CODE)
        activate_real_mode(key, DEFAULT_BRANCH_CODE)

        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Fetch admin and barista users
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = 'admin'")
            cls.admin_user = dict(cursor.fetchone())
            cursor.execute("SELECT * FROM users WHERE username = 'barista_elvin'")
            cls.barista_user = dict(cursor.fetchone())
            cursor.execute("SELECT * FROM users WHERE username = 'developer'")
            cls.dev_user = dict(cursor.fetchone())

        cls.admin_token = create_access_token({
            "sub": str(cls.admin_user["id"]),
            "username": cls.admin_user["username"],
            "role": cls.admin_user["role"],
            "full_name": cls.admin_user["full_name"],
            "branch_id": cls.admin_user["branch_id"],
        })

        cls.barista_token = create_access_token({
            "sub": str(cls.barista_user["id"]),
            "username": cls.barista_user["username"],
            "role": cls.barista_user["role"],
            "full_name": cls.barista_user["full_name"],
            "branch_id": cls.barista_user["branch_id"],
        })

        cls.dev_token = create_access_token({
            "sub": str(cls.dev_user["id"]),
            "username": cls.dev_user["username"],
            "role": cls.dev_user["role"],
            "full_name": cls.dev_user["full_name"],
            "branch_id": cls.dev_user["branch_id"],
        })

    # --- 1. Products & Variants Creation & Deletion ---
    def test_create_and_delete_product_and_variants(self):
        """Test creating a new product with variants, deleting a variant, and deleting the product."""
        # Create product
        payload = {
            "name": "Test Matcha Latte",
            "category": "İsti İçkilər",
            "description": "Premium Uji Matcha",
            "image_url": "/static/images/icons/tea.png",
            "variants": [
                {"name": "Kiçik (Small)", "price": 6.50},
                {"name": "Böyük (Large)", "price": 8.50},
            ]
        }
        res = self.client.post(
            "/api/products",
            data=json.dumps(payload),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertIn(res.status_code, (200, 201))
        data = res.get_json()
        self.assertIn("product", data)
        prod_id = data["product"]["id"]

        # Verify in database
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM product_variants WHERE product_id = ?", (prod_id,))
            variants = cursor.fetchall()
            self.assertEqual(len(variants), 2)
            var1_id = variants[0]["id"]
            var2_id = variants[1]["id"]

        # Delete one variant
        res_del_var = self.client.delete(
            f"/api/products/variants/{var1_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res_del_var.status_code, 200)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM product_variants WHERE id = ?", (var1_id,))
            self.assertIsNone(cursor.fetchone())
            cursor.execute("SELECT * FROM product_variants WHERE id = ?", (var2_id,))
            self.assertIsNotNone(cursor.fetchone())

        # Delete entire product
        res_del_prod = self.client.delete(
            f"/api/products/{prod_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res_del_prod.status_code, 200)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM products WHERE id = ?", (prod_id,))
            self.assertIsNone(cursor.fetchone())
            cursor.execute("SELECT * FROM product_variants WHERE product_id = ?", (prod_id,))
            self.assertEqual(len(cursor.fetchall()), 0)

    # --- 2. Stock CRUD: Update & Delete Raw Material ---
    def test_stock_update_and_delete(self):
        """Test updating raw material stock details & balance, and deleting unused material."""
        # Create a test raw material first
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO raw_materials (branch_id, name, category, unit, current_stock, minimum_alert_threshold, cost_per_unit)
                VALUES (1, 'Test Qənd Şərbəti', 'Sirop və Dadlandırıcılar', 'ml', 500.0, 100.0, 0.01)
                """
            )
            mat_id = cursor.lastrowid

        # Update stock item (change details + adjust current_stock from 500 to 750)
        update_payload = {
            "name": "Test Qənd Şərbəti (Premium)",
            "category": "Sirop və Dadlandırıcılar",
            "unit": "ml",
            "current_stock": 750.0,
            "minimum_alert_threshold": 120.0,
            "cost_per_unit": 0.015,
            "notes": "Sayım düzəlişi: +250ml tapıldı"
        }
        res_update = self.client.put(
            f"/api/stock/{mat_id}",
            data=json.dumps(update_payload),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res_update.status_code, 200)

        # Check stock balance and transactions
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM raw_materials WHERE id = ?", (mat_id,))
            updated_mat = dict(cursor.fetchone())
            self.assertEqual(updated_mat["name"], "Test Qənd Şərbəti (Premium)")
            self.assertEqual(updated_mat["current_stock"], 750.0)
            self.assertEqual(updated_mat["minimum_alert_threshold"], 120.0)

            # Check stock adjustment transaction log
            cursor.execute("SELECT * FROM stock_transactions WHERE raw_material_id = ?", (mat_id,))
            tx = cursor.fetchone()
            self.assertIsNotNone(tx)
            self.assertEqual(tx["change_amount"], 250.0)
            self.assertEqual(tx["reference_type"], "inventory_adjustment")

        # Delete the test material
        res_del = self.client.delete(
            f"/api/stock/{mat_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res_del.status_code, 200)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM raw_materials WHERE id = ?", (mat_id,))
            self.assertIsNone(cursor.fetchone())

    # --- 3. Recipe Management & Deletions ---
    def test_recipe_ingredient_deletion_and_clearing(self):
        """Test deleting individual recipe ingredient and clearing entire recipe."""
        # Find an existing variant with recipe
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT variant_id FROM recipes LIMIT 1")
            row = cursor.fetchone()
            variant_id = row["variant_id"]

            cursor.execute("SELECT id FROM recipes WHERE variant_id = ?", (variant_id,))
            recipe_ids = [r["id"] for r in cursor.fetchall()]
            target_recipe_id = recipe_ids[0]

        # Delete single recipe ingredient
        res_del_ing = self.client.delete(
            f"/api/recipes/{target_recipe_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res_del_ing.status_code, 200)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM recipes WHERE id = ?", (target_recipe_id,))
            self.assertIsNone(cursor.fetchone())

        # Clear entire recipe for this variant
        res_clear = self.client.delete(
            f"/api/recipes/variant/{variant_id}",
            headers={"Authorization": f"Bearer {self.admin_token}"}
        )
        self.assertEqual(res_clear.status_code, 200)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM recipes WHERE variant_id = ?", (variant_id,))
            self.assertEqual(len(cursor.fetchall()), 0)

    # --- 4. User Shortcuts Management ---
    def test_user_shortcuts_crud_and_reordering(self):
        """Test adding, editing, reordering, and deleting shortcuts."""
        # 1. Get shortcuts
        res_get = self.client.get(
            "/api/shortcuts",
            headers={"Authorization": f"Bearer {self.barista_token}"}
        )
        self.assertEqual(res_get.status_code, 200)

        # 2. Add a new shortcut
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM product_variants LIMIT 1")
            var_id = cursor.fetchone()["id"]

        add_payload = {
            "variant_id": var_id,
            "custom_label": "Xüsusi Sürətli Düymə",
            "icon_url": "/static/images/icons/croissant.png"
        }
        res_add = self.client.post(
            "/api/shortcuts/add",
            data=json.dumps(add_payload),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.barista_token}"}
        )
        self.assertIn(res_add.status_code, (200, 201))
        new_sc_id = res_add.get_json()["shortcut_id"]

        # 3. Update the shortcut
        edit_payload = {
            "custom_label": "Yenilənmiş Düymə",
            "icon_url": "/static/images/icons/dessert.png"
        }
        res_edit = self.client.put(
            f"/api/shortcuts/{new_sc_id}",
            data=json.dumps(edit_payload),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.barista_token}"}
        )
        self.assertEqual(res_edit.status_code, 200)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_shortcuts WHERE id = ?", (new_sc_id,))
            sc = dict(cursor.fetchone())
            self.assertEqual(sc["custom_label"], "Yenilənmiş Düymə")
            self.assertEqual(sc["icon_url"], "/static/images/icons/dessert.png")

        # 4. Reorder shortcuts
        reorder_payload = {"ordered_ids": [new_sc_id]}
        res_reorder = self.client.post(
            "/api/shortcuts/reorder",
            data=json.dumps(reorder_payload),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.barista_token}"}
        )
        self.assertEqual(res_reorder.status_code, 200)

        # 5. Remove the shortcut
        res_del_sc = self.client.delete(
            f"/api/shortcuts/{new_sc_id}",
            headers={"Authorization": f"Bearer {self.barista_token}"}
        )
        self.assertEqual(res_del_sc.status_code, 200)

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_shortcuts WHERE id = ?", (new_sc_id,))
            self.assertIsNone(cursor.fetchone())

    # --- 5. Profile Security: Mandatory current_password Check ---
    def test_profile_update_enforces_current_password(self):
        """Profile update (avatar or password) must strictly require valid current_password."""
        # Attempt without current_password
        res_missing = self.client.put(
            "/api/auth/profile",
            data=json.dumps({"avatar_url": "/static/avatars/barista_3.png"}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.barista_token}"}
        )
        self.assertEqual(res_missing.status_code, 400)
        self.assertIn("cari şifrə", res_missing.get_json()["message"].lower())

        # Attempt with wrong current_password
        res_wrong = self.client.put(
            "/api/auth/profile",
            data=json.dumps({
                "avatar_url": "/static/avatars/barista_3.png",
                "current_password": "completely_wrong_pw!"
            }),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.barista_token}"}
        )
        self.assertEqual(res_wrong.status_code, 400)
        self.assertIn("cari şifrə", res_wrong.get_json()["message"].lower())

        # Attempt with correct current_password ('barista123!')
        res_ok = self.client.put(
            "/api/auth/profile",
            data=json.dumps({
                "avatar_url": "/static/avatars/barista_3.png",
                "current_password": "barista123!"
            }),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.barista_token}"}
        )
        self.assertEqual(res_ok.status_code, 200)
        self.assertTrue(res_ok.get_json()["success"])

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT avatar_url FROM users WHERE id = ?", (self.barista_user["id"],))
            self.assertEqual(cursor.fetchone()["avatar_url"], "/static/avatars/barista_3.png")

    # --- 6. Developer Authenticated Downloads (Headers and ?token=) ---
    def test_developer_downloads_authenticated(self):
        """Test SQL, JSON, TXT exports and Remote Server ZIP package download."""
        # A. Via Bearer header
        # SQL export
        res_sql = self.client.get(
            "/api/developer/export/sql",
            headers={"Authorization": f"Bearer {self.dev_token}"}
        )
        self.assertEqual(res_sql.status_code, 200)
        self.assertIn("CREATE TABLE", res_sql.get_data(as_text=True))

        # JSON export
        res_json = self.client.get(
            "/api/developer/export/json",
            headers={"Authorization": f"Bearer {self.dev_token}"}
        )
        self.assertEqual(res_json.status_code, 200)
        parsed_json = json.loads(res_json.get_data(as_text=True))
        self.assertIn("branches", parsed_json)

        # TXT tree export
        res_txt = self.client.get(
            "/api/developer/export/txt",
            headers={"Authorization": f"Bearer {self.dev_token}"}
        )
        self.assertEqual(res_txt.status_code, 200)
        self.assertIn("STRUKTUR", res_txt.get_data(as_text=True))

        # Remote server ZIP package
        res_zip = self.client.get(
            "/api/sync/download-package",
            headers={"Authorization": f"Bearer {self.dev_token}"}
        )
        self.assertEqual(res_zip.status_code, 200)
        self.assertEqual(res_zip.mimetype, "application/zip")
        with zipfile.ZipFile(io.BytesIO(res_zip.data)) as zf:
            namelist = zf.namelist()
            self.assertIn("server.py", namelist)

        # B. Via query param ?token= (No Authorization header)
        res_sql_param = self.client.get(f"/api/developer/export/sql?token={self.dev_token}")
        self.assertEqual(res_sql_param.status_code, 401)

        res_zip_param = self.client.get(f"/api/sync/download-package?token={self.dev_token}")
        self.assertEqual(res_zip_param.status_code, 401)

    # --- 7. System Health Toggles (AES-256 and GZ compression) ---
    def test_system_health_toggles_persist(self):
        """Test toggling AES-256 encryption and GZ compression in developer settings."""
        # 1. Toggle encryption ON
        res_enc_on = self.client.post(
            "/api/developer/encryption",
            data=json.dumps({"enabled": True}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.dev_token}"}
        )
        self.assertEqual(res_enc_on.status_code, 200)
        self.assertTrue(res_enc_on.get_json()["success"])

        # 2. Toggle compression ON
        res_gz_on = self.client.post(
            "/api/developer/compression",
            data=json.dumps({"enabled": True}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.dev_token}"}
        )
        self.assertEqual(res_gz_on.status_code, 200)
        self.assertTrue(res_gz_on.get_json()["success"])

        # 3. Check diagnostics endpoint reflects both as active
        res_diag = self.client.get(
            "/api/developer/diagnostics",
            headers={"Authorization": f"Bearer {self.dev_token}"}
        )
        self.assertEqual(res_diag.status_code, 200)
        features = res_diag.get_json()["features"]
        self.assertTrue(features["encryption_enabled"])
        self.assertTrue(features["compression_enabled"])

        # 4. Toggle both OFF
        res_enc_off = self.client.post(
            "/api/developer/encryption",
            data=json.dumps({"enabled": False}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.dev_token}"}
        )
        self.assertEqual(res_enc_off.status_code, 200)

        res_gz_off = self.client.post(
            "/api/developer/compression",
            data=json.dumps({"enabled": False}),
            content_type="application/json",
            headers={"Authorization": f"Bearer {self.dev_token}"}
        )
        self.assertEqual(res_gz_off.status_code, 200)

        res_diag_off = self.client.get(
            "/api/developer/diagnostics",
            headers={"Authorization": f"Bearer {self.dev_token}"}
        )
        self.assertEqual(res_diag_off.status_code, 200)
        features_off = res_diag_off.get_json()["features"]
        self.assertFalse(features_off["encryption_enabled"])
        self.assertFalse(features_off["compression_enabled"])

if __name__ == "__main__":
    unittest.main()
