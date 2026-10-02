"""
Unit and Integration Tests: Raw Material Stock Truth, Flexible Recipes, and Deductions
"""
import unittest
from app.main import create_app
from app.core.database import get_db
from app.auth.auth import login_other_service
from seed import seed_database

class TestStockAndRecipes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

        # Login as barista
        res, _ = login_other_service("barista_elvin", "barista123!")
        cls.barista_token = res["token"]

    def test_order_deducts_exact_raw_materials_from_recipe(self):
        """CRITICAL RULE E1 & E2: Selling a drink deducts raw materials according to exact recipe."""
        with get_db() as conn:
            # Find Latte Large Takeaway variant
            var = conn.execute(
                """
                SELECT v.id, v.price, p.name as prod_name, v.name as var_name
                FROM product_variants v
                JOIN products p ON v.product_id = p.id
                WHERE p.name = 'Caffè Latte' AND v.name = 'Böyük Takeaway'
                """
            ).fetchone()
            self.assertIsNotNone(var)
            variant_id = var["id"]

            # Query baseline stock for Coffee and Milk
            coffee_before = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Illy Espresso Dənələri (Classico)'").fetchone()["current_stock"]
            milk_before = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Tam Yağlı Təbii Süd (3.2%)'").fetchone()["current_stock"]
            cup_before = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Böyük Kağız Stəkan (12oz / 350ml)'").fetchone()["current_stock"]
            lid_before = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Böyük Stəkan Qapağı'").fetchone()["current_stock"]

        # Order 2x Latte Large Takeaway
        # Recipe per item: 22g coffee, 260ml milk, 1 cup, 1 lid
        # Deduction for 2: 44g coffee, 520ml milk, 2 cups, 2 lids
        order_payload = {
            "items": [
                {
                    "variant_id": variant_id,
                    "product_name": var["prod_name"],
                    "variant_name": var["var_name"],
                    "unit_price": var["price"],
                    "quantity": 2,
                }
            ],
            "discount_type": "none",
            "payment_method": "cash",
        }

        resp = self.client.post(
            "/api/orders",
            json=order_payload,
            headers={"Authorization": f"Bearer {self.barista_token}"},
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertTrue("order_id" in data)

        # Verify exact stock deduction
        with get_db() as conn:
            coffee_after = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Illy Espresso Dənələri (Classico)'").fetchone()["current_stock"]
            milk_after = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Tam Yağlı Təbii Süd (3.2%)'").fetchone()["current_stock"]
            cup_after = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Böyük Kağız Stəkan (12oz / 350ml)'").fetchone()["current_stock"]
            lid_after = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Böyük Stəkan Qapağı'").fetchone()["current_stock"]

            self.assertAlmostEqual(coffee_before - coffee_after, 44.0, places=2)
            self.assertAlmostEqual(milk_before - milk_after, 520.0, places=2)
            self.assertAlmostEqual(cup_before - cup_after, 2.0, places=2)
            self.assertAlmostEqual(lid_before - lid_after, 2.0, places=2)

            # Verify ledger transactions recorded
            txs = conn.execute("SELECT * FROM stock_transactions WHERE reference_type = 'order' AND reference_id = ?", (data["order_id"],)).fetchall()
            self.assertEqual(len(txs), 4)

    def test_restock_increases_quantity_and_records_ledger(self):
        """Admin can restock raw materials and track intake ledger."""
        res, _ = login_other_service("admin", "admin123!")
        admin_token = res["token"]

        with get_db() as conn:
            mat = conn.execute("SELECT id, current_stock FROM raw_materials WHERE name = 'Klassik Kərə Yağlı Kruasan'").fetchone()
            before = mat["current_stock"]

        resp = self.client.post(
            f"/api/stock/{mat['id']}/restock",
            json={"quantity": 25.0, "notes": "Səhər təzə bişmiş kruasan partiyası"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(resp.status_code, 200)

        with get_db() as conn:
            after = conn.execute("SELECT current_stock FROM raw_materials WHERE id = ?", (mat["id"],)).fetchone()["current_stock"]
            self.assertAlmostEqual(after - before, 25.0, places=2)

if __name__ == "__main__":
    unittest.main()

