import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import create_app
from models import Order, db
from receipt_pdf import build_receipt_pdf
from routes.orders import _serialize_order


class TestReceiptPdfRendering(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "receipt-pdf-test.sqlite"
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
                "PICKUP_OPEN_HOUR": 0,
                "PICKUP_OPEN_MINUTE": 0,
                "PICKUP_CLOSE_HOUR": 23,
                "PICKUP_CLOSE_MINUTE": 59,
            }
        )
        self.client = self.app.test_client()
        self.base_now = datetime.now(ZoneInfo(self.app.config["APP_TIMEZONE"])).replace(
            hour=12,
            minute=0,
            second=0,
            microsecond=0,
        )
        self._now_patch = patch("routes.orders._now_local", return_value=self.base_now)
        self._now_patch.start()
        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self) -> None:
        self._now_patch.stop()
        self.tmpdir.cleanup()

    def _first_menu_item(self) -> dict:
        menu = self.client.get("/api/menu").get_json()
        return menu["categories"][0]["items"][0]

    def _seed_cart(self, quantity: int = 2) -> None:
        item = self._first_menu_item()
        with self.client.session_transaction() as session:
            session["cart_lines"] = [{"id": item["id"], "qty": quantity}]

    def _scheduled_form(self) -> dict[str, str]:
        pickup = (self.base_now + timedelta(days=1)).replace(
            hour=12, minute=30, second=0, microsecond=0
        )
        return {
            "customer_name": "Receipt Tester",
            "customer_email": "receipt@example.com",
            "customer_phone": "0412 345 678",
            "fulfillment_type": "scheduled",
            "pickup_date": pickup.strftime("%Y-%m-%d"),
            "pickup_time": pickup.strftime("%H:%M"),
            "payment_method": "card",
            "card_name": "Receipt Tester",
            "card_number": "4242 4242 4242 4242",
            "card_expiry": "12/30",
            "card_cvv": "123",
            "special_instructions": "Please keep the soup separate.",
        }

    def _instant_form(self) -> dict[str, str]:
        return {
            "customer_name": "Queue Tester",
            "customer_email": "queue@example.com",
            "customer_phone": "0412 345 678",
            "fulfillment_type": "instant",
            "pickup_date": "",
            "pickup_time": "",
            "payment_method": "card",
            "card_name": "Queue Tester",
            "card_number": "4242 4242 4242 4242",
            "card_expiry": "12/30",
            "card_cvv": "123",
            "special_instructions": "",
        }

    def _place_order(self, form_data: dict[str, str]) -> str:
        self._seed_cart()
        response = self.client.post("/checkout", data=form_data, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        return response.headers["Location"].split("order=")[-1]

    def _order_payload(self, order_number: str) -> dict:
        with self.app.app_context():
            order = Order.query.filter_by(order_number=order_number).first()
            self.assertIsNotNone(order)
            return _serialize_order(order)

    def test_scheduled_receipt_renders_valid_pdf(self):
        order_number = self._place_order(self._scheduled_form())
        with self.app.test_request_context():
            payload = self._order_payload(order_number)
            pdf_bytes = build_receipt_pdf(payload)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_instant_receipt_renders_valid_pdf(self):
        order_number = self._place_order(self._instant_form())
        with self.app.test_request_context():
            payload = self._order_payload(order_number)
            pdf_bytes = build_receipt_pdf(payload)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertTrue(payload["is_instant"])
        self.assertIsNotNone(payload["queue_display"])

    def test_receipt_endpoint_returns_pdf(self):
        order_number = self._place_order(self._scheduled_form())
        response = self.client.get(f"/orders/{order_number}/receipt.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        data = response.get_data()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 1000)

    def test_receipt_pdf_handles_many_line_items_pagination(self):
        menu = self.client.get("/api/menu").get_json()
        unique_items: list[dict] = []
        for category in menu["categories"]:
            for item in category["items"]:
                unique_items.append(item)
                if len(unique_items) >= 18:
                    break
            if len(unique_items) >= 18:
                break

        with self.client.session_transaction() as session:
            session["cart_lines"] = [
                {"id": item["id"], "qty": 1} for item in unique_items
            ]

        response = self.client.post(
            "/checkout",
            data=self._scheduled_form(),
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        order_number = response.headers["Location"].split("order=")[-1]

        with self.app.test_request_context():
            payload = self._order_payload(order_number)
            pdf_bytes = build_receipt_pdf(payload)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(payload["lines"]), 10)


if __name__ == "__main__":
    unittest.main()
