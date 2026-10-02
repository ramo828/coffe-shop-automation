"""
Unit and Integration Tests: Orders, Cart, Discounts, and Void/Cancellation Reversal
"""
import unittest
from app.main import create_app
from app.core.database import get_db
from app.auth.auth import login_other_service
from seed import seed_database

class TestOrdersAndVoid(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed_database()
        cls.app = create_app()
        cls.client = cls.app.test_client()

        res, _ = login_other_service("barista_elvin", "barista123!")
        cls.barista_token = res["token"]

    def test_order_cancellation_and_accurate_stock_reversal(self):
        """CRITICAL RULE F3: Order cancellation reverses stock and preserves trace."""
        with get_db() as conn:
            var = conn.execute(
                """
                SELECT v.id, v.price, p.name as prod_name, v.name as var_name
                FROM product_variants v JOIN products p ON v.product_id = p.id
                WHERE p.name = 'Americano' AND v.name = 'Kiçik (Small)'
                """
            ).fetchone()
            # Americano Small takes 18g coffee, 1 small cup, 1 small lid
            coffee_before = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Illy Espresso Dənələri (Classico)'").fetchone()["current_stock"]

        # Create Order
        resp = self.client.post(
            "/api/orders",
            json={
                "items": [
                    {
                        "variant_id": var["id"],
                        "product_name": var["prod_name"],
                        "variant_name": var["var_name"],
                        "unit_price": var["price"],
                        "quantity": 1,
                    }
                ],
                "discount_type": "none",
                "payment_method": "card",
            },
            headers={"Authorization": f"Bearer {self.barista_token}"},
        )
        self.assertEqual(resp.status_code, 201)
        order_id = resp.get_json()["order_id"]

        with get_db() as conn:
            coffee_after_order = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Illy Espresso Dənələri (Classico)'").fetchone()["current_stock"]
            self.assertAlmostEqual(coffee_before - coffee_after_order, 18.0, places=2)

        # Cancel Order
        cancel_resp = self.client.post(
            f"/api/orders/{order_id}/cancel",
            json={"reason": "Müştəri nağd ödəmək istədi, yenidən vurulacaq"},
            headers={"Authorization": f"Bearer {self.barista_token}"},
        )
        self.assertEqual(cancel_resp.status_code, 200)

        # Verify order is NOT hard-deleted, but marked status='cancelled'
        with get_db() as conn:
            order_row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            self.assertEqual(order_row["status"], "cancelled")
            self.assertEqual(order_row["cancel_reason"], "Müştəri nağd ödəmək istədi, yenidən vurulacaq")

            # Verify stock was accurately restored back to original level!
            coffee_after_cancel = conn.execute("SELECT current_stock FROM raw_materials WHERE name = 'Illy Espresso Dənələri (Classico)'").fetchone()["current_stock"]
            self.assertAlmostEqual(coffee_after_cancel, coffee_before, places=2)

            # Check reversal transaction recorded in ledger
            tx = conn.execute(
                "SELECT * FROM stock_transactions WHERE reference_type = 'order_cancel' AND reference_id = ?",
                (order_id,),
            ).fetchone()
            self.assertIsNotNone(tx)
            self.assertEqual(tx["change_amount"], 18.0)

    def test_internal_ticket_formatting(self):
        """CRITICAL RULE F6: Internal non-fiscal ticket format generated."""
        with get_db() as conn:
            var = conn.execute("SELECT id, price, name FROM product_variants LIMIT 1").fetchone()

        resp = self.client.post(
            "/api/orders",
            json={
                "items": [
                    {
                        "variant_id": var["id"],
                        "product_name": "Espresso Illy",
                        "variant_name": var["name"],
                        "unit_price": var["price"],
                        "quantity": 1,
                    }
                ],
                "discount_type": "percent",
                "discount_value": 10.0,
                "payment_method": "cash",
            },
            headers={"Authorization": f"Bearer {self.barista_token}"},
        )
        data = resp.get_json()
        ticket = data["ticket"]
        self.assertIn("DAXİLİ SİFARİŞ QƏBZİ", ticket["text_ticket"])
        self.assertIn("QEYRİ-FİSKAL", ticket["text_ticket"])

if __name__ == "__main__":
    unittest.main()

