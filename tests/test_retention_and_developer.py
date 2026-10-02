"""
Unit and Integration Tests: Data Retention Safety, Developer Exports, and Remote ZIP Packager
"""
import unittest
import io
import zipfile
import json
from app.core.retention import set_retention_policy, execute_retention_cleanup, get_current_retention_policy
from app.core.database import get_db
from app.developer.developer import export_db_sql, export_db_json, export_db_tree_txt
from app.sync.remote_packager import generate_remote_code_zip
from app.security.license import activate_real_mode, generate_activation_key
from app.core.config import DEFAULT_BRANCH_CODE
from seed import seed_database

class TestRetentionAndDeveloper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        # Activate REAL mode for export tests
        valid_key = generate_activation_key(DEFAULT_BRANCH_CODE)
        activate_real_mode(valid_key, DEFAULT_BRANCH_CODE)

    def test_retention_cleanup_strictly_protects_critical_tables(self):
        """CRITICAL RULE M3: Retention MUST NOT wipe ML models, accounts, stock master, or recipes."""
        set_retention_policy("1_week")
        self.assertEqual(get_current_retention_policy(), "1_week")

        res = execute_retention_cleanup()
        self.assertTrue(res["purged"])

        with get_db() as conn:
            # 1. Users must be intact
            users_cnt = conn.execute("SELECT count(*) FROM users").fetchone()[0]
            self.assertGreaterEqual(users_cnt, 3)

            # 2. ML models must be intact
            ml_cnt = conn.execute("SELECT count(*) FROM ml_models").fetchone()[0]
            self.assertGreaterEqual(ml_cnt, 1)

            # 3. Raw materials must be intact
            mat_cnt = conn.execute("SELECT count(*) FROM raw_materials").fetchone()[0]
            self.assertGreaterEqual(mat_cnt, 10)

            # 4. Recipes must be intact
            recipes_cnt = conn.execute("SELECT count(*) FROM recipes").fetchone()[0]
            self.assertGreaterEqual(recipes_cnt, 10)

    def test_developer_real_mode_exports(self):
        """CRITICAL RULE M5: In REAL mode, Developer can export as .sql, .json, and .txt tree."""
        # 1. SQL Export
        sql_dump, msg = export_db_sql()
        self.assertIsNotNone(sql_dump)
        self.assertIn("CREATE TABLE", sql_dump)
        self.assertIn("INSERT INTO", sql_dump)

        # 2. JSON Export
        json_dump, msg = export_db_json()
        self.assertIsNotNone(json_dump)
        data = json.loads(json_dump)
        self.assertIn("branches", data)
        self.assertIn("menu_catalog", data)
        self.assertIn("raw_materials", data)

        # 3. TXT Tree Structure
        txt_tree, msg = export_db_tree_txt()
        self.assertIsNotNone(txt_tree)
        self.assertIn("STRUKTUR VƏ MƏLUMAT AĞACI", txt_tree)
        self.assertIn("├── [Filiallar]", txt_tree)
        self.assertIn("├── [İşçi Heyəti]", txt_tree)
        self.assertIn("├── [Menyu və Reseptlər]", txt_tree)

    def test_remote_code_packager_zip(self):
        """CRITICAL RULE K3: Generate downloadable standalone remote Python API package ZIP."""
        zip_bytes = generate_remote_code_zip()
        self.assertIsNotNone(zip_bytes)

        # Verify ZIP archive structure
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            namelist = zf.namelist()
            self.assertIn("server.py", namelist)
            self.assertIn("schema.sql", namelist)
            self.assertIn("remote_config.json", namelist)
            self.assertIn("requirements.txt", namelist)
            self.assertIn("README.md", namelist)

            # Verify server.py has endpoints
            server_content = zf.read("server.py").decode("utf-8")
            self.assertIn("/api/health", server_content)
            self.assertIn("/api/sync/batch", server_content)

if __name__ == "__main__":
    unittest.main()

