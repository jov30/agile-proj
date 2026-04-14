import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from app import create_app
from models import Order, db


class TestCheckoutAndOrders(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "orders-test.sqlite"
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            }
        )
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _first_menu_item(self) -> dict:
        menu = self.client.get("/api/menu").get_json()
        return menu["categories"][0]["items"][0]

    def _seed_cart(self, quantity: int = 2) -> dict:
        item = self._first_menu_item()
        with self.client.session_transaction() as session:
            session["cart_lines"] = [{"id": item["id"], "qty": quantity}]
        return item

    def _valid_checkout_form(self) -> dict[str, str]:
        now = datetime.now(ZoneInfo(self.app.config["APP_TIMEZONE"]))
        pickup = (now + timedelta(days=1)).replace(
            hour=12,
            minute=30,
            second=0,
            microsecond=0,
        )
        return {
            "customer_name": "Nguyen Tester",
            "customer_email": "tester@example.com",
            "customer_phone": "0412 345 678",
            "pickup_date": pickup.strftime("%Y-%m-%d"),
            "pickup_time": pickup.strftime("%H:%M"),
            "payment_method": "card",
            "card_name": "Nguyen Tester",
            "card_number": "4242 4242 4242 4242",
            "card_expiry": "12/30",
            "card_cvv": "123",
            "special_instructions": "Please keep the soup separate.",
        }

    def _place_order(self) -> str:
        self._seed_cart()
        response = self.client.post("/checkout", data=self._valid_checkout_form(), follow_redirects=False)
        self.assertEqual(response.status_code, 302)

        location = response.headers["Location"]
        query = parse_qs(urlparse(location).query)
        order_number = query["order"][0]

        with self.app.app_context():
            order = Order.query.filter_by(order_number=order_number).first()
            self.assertIsNotNone(order)
            return order_number

    def test_checkout_page_renders_summary_from_cart(self):
        item = self._seed_cart()
        response = self.client.get("/checkout")
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("Pay", text)
        self.assertIn(item["name"], text)

    def test_checkout_submission_creates_order_and_clears_cart(self):
        self._seed_cart()
        response = self.client.post("/checkout", data=self._valid_checkout_form(), follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/receipt?order=", response.headers["Location"])

        with self.app.app_context():
            order = Order.query.one()
            self.assertEqual(order.order_status, "Confirmed")
            self.assertEqual(order.payment_status, "Paid (simulated)")
            self.assertEqual(len(order.line_items), 1)

        with self.client.session_transaction() as session:
            self.assertEqual(session.get("cart_lines"), [])
            self.assertIn("last_order_number", session)
            self.assertEqual(len(session.get("order_history_numbers", [])), 1)

    def test_receipt_page_pdf_and_api_work_for_created_order(self):
        order_number = self._place_order()

        receipt = self.client.get(f"/receipt?order={order_number}")
        self.assertEqual(receipt.status_code, 200)
        self.assertIn(order_number, receipt.get_data(as_text=True))

        pdf = self.client.get(f"/orders/{order_number}/receipt.pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.mimetype, "application/pdf")
        self.assertTrue(pdf.data.startswith(b"%PDF"))

        api_detail = self.client.get(f"/api/orders/{order_number}")
        self.assertEqual(api_detail.status_code, 200)
        self.assertEqual(api_detail.get_json()["order_number"], order_number)

    def test_order_history_and_reorder_flow(self):
        order_number = self._place_order()

        history = self.client.get("/orders")
        self.assertEqual(history.status_code, 200)
        text = history.get_data(as_text=True)
        self.assertIn(order_number, text)
        self.assertIn("Order again", text)

        api_orders = self.client.get("/api/orders")
        self.assertEqual(api_orders.status_code, 200)
        payload = api_orders.get_json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["orders"][0]["order_number"], order_number)

        reorder = self.client.post(f"/orders/{order_number}/reorder", follow_redirects=False)
        self.assertEqual(reorder.status_code, 302)
        self.assertEqual(reorder.headers["Location"], "/checkout")
        with self.client.session_transaction() as session:
            self.assertEqual(len(session.get("cart_lines", [])), 1)

    def test_checkout_validation_rejects_empty_cart(self):
        response = self.client.post("/checkout", data=self._valid_checkout_form())
        self.assertEqual(response.status_code, 400)
        self.assertIn("Your cart is empty", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
