"""
Unit and Integration Tests: Authentication, Roles, GNOME Profile Picker, and Password Security
"""
import unittest
from app.main import create_app
from app.core.database import get_db
from app.auth.auth import get_visible_profiles_service, login_other_service, login_by_profile_service
from seed import seed_database
from app.core.config import DEVELOPER_CODE_PASSWORD

class TestAuthAndRoles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_gnome_profile_picker_excludes_developer(self):
        """CRITICAL RULE D3: Developer account must NOT appear in the visible profile list!"""
        profiles = get_visible_profiles_service()
        roles = [p["role"] for p in profiles]
        self.assertNotIn("developer", roles)

        # Admin and Barista must be present
        self.assertIn("admin", roles)
        self.assertIn("barista", roles)

        # Check via HTTP endpoint
        resp = self.client.get("/api/auth/profiles")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        for p in data:
            self.assertNotEqual(p["role"], "developer")

    def test_developer_login_via_other(self):
        """CRITICAL RULE D4: Developer logs in via 'Other' / 'Digər' option."""
        res, msg = login_other_service("developer", DEVELOPER_CODE_PASSWORD)
        self.assertIsNotNone(res)
        self.assertEqual(res["user"]["role"], "developer")
        self.assertTrue("token" in res)

    def test_developer_cannot_login_via_profile_card(self):
        """Developer cannot be logged in via normal profile picker."""
        with get_db() as conn:
            dev = conn.execute("SELECT id FROM users WHERE role = 'developer'").fetchone()
        res, msg = login_by_profile_service(dev["id"], DEVELOPER_CODE_PASSWORD)
        self.assertIsNone(res)

    def test_password_cannot_be_viewed_by_anyone(self):
        """CRITICAL RULE C3: All passwords stored hashed, no role can view passwords."""
        with get_db() as conn:
            users = conn.execute("SELECT * FROM users").fetchall()
            for u in users:
                # Must be bcrypt hash string, never plaintext
                self.assertTrue(u["password_hash"].startswith("$2b$"))
                self.assertNotIn("123", u["password_hash"])

        # Check API users list does not expose password_hash
        dev_res, _ = login_other_service("developer", DEVELOPER_CODE_PASSWORD)
        token = dev_res["token"]
        resp = self.client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        user_list = resp.get_json()
        for u in user_list:
            self.assertNotIn("password", u)
            self.assertNotIn("password_hash", u)

if __name__ == "__main__":
    unittest.main()
