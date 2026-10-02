"""
Unit and Integration Tests: Shifts and Physical Inventory Count Auditing
"""
import unittest
from app.main import create_app
from app.core.database import get_db
from app.auth.auth import login_other_service
from seed import seed_database

class TestShiftsAndInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

        res, _ = login_other_service("admin", "admin123!")
        cls.admin_token = res["token"]

    def test_inventory_count_session_and_adjustments(self):
        """CRITICAL RULE H: Physical stock counting, variance detection and confirmation."""
        # 1. Start inventory session
        resp = self.client.post(
            "/api/inventory/start",
            json={"notes": "Həftəlik inventarizasiya testi"},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(resp.status_code, 201)
        session = resp.get_json()
        count_id = session["id"]

        # 2. Find a material to simulate variance (e.g. spillage / waste of milk)
        item_to_adjust = None
        for itm in session["items"]:
            if "Süd" in itm["material_name"]:
                item_to_adjust = itm
                break
        self.assertIsNotNone(item_to_adjust)

        sys_qty = item_to_adjust["system_quantity"]
        counted_qty = sys_qty - 500.0  # 500ml spillage/waste

        # 3. Update count draft
        update_resp = self.client.put(
            f"/api/inventory/{count_id}",
            json={"items": [{"id": item_to_adjust["id"], "counted_quantity": counted_qty, "notes": "Dağılma/Tullantı"}]},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(update_resp.status_code, 200)

        # 4. Confirm adjustments
        confirm_resp = self.client.post(
            f"/api/inventory/{count_id}/confirm",
            json={"notes": "İnventarizasiya təsdiqləndi"},
            headers={"Authorization": f"Bearer {self.admin_token}"},
        )
        self.assertEqual(confirm_resp.status_code, 200)

        # 5. Verify raw material stock updated to counted_qty and adjustment logged
        with get_db() as conn:
            mat = conn.execute("SELECT current_stock FROM raw_materials WHERE id = ?", (item_to_adjust["raw_material_id"],)).fetchone()
            self.assertAlmostEqual(mat["current_stock"], counted_qty, places=2)

            tx = conn.execute(
                "SELECT * FROM stock_transactions WHERE reference_type = 'inventory_adjustment' AND reference_id = ?",
                (count_id,),
            ).fetchone()
            self.assertIsNotNone(tx)
            self.assertAlmostEqual(tx["change_amount"], -500.0, places=2)

if __name__ == "__main__":
    unittest.main()

