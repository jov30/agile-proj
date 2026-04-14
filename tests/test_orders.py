import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from app import create_app
from models import Order, PaymentAttempt, db


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

    def _valid_checkout_form(
        self,
        *,
        days_ahead: int = 1,
        fulfillment_type: str = "scheduled",
        card_number: str = "4242 4242 4242 4242",
        special_instructions: str = "Please keep the soup separate.",
    ) -> dict[str, str]:
        now = datetime.now(ZoneInfo(self.app.config["APP_TIMEZONE"]))
        pickup = (now + timedelta(days=days_ahead)).replace(
            hour=12,
            minute=30,
            second=0,
            microsecond=0,
        )
        form = {
            "customer_name": "Nguyen Tester",
            "customer_email": "tester@example.com",
            "customer_phone": "0412 345 678",
            "fulfillment_type": fulfillment_type,
            "pickup_date": pickup.strftime("%Y-%m-%d"),
            "pickup_time": pickup.strftime("%H:%M"),
            "payment_method": "card",
            "card_name": "Nguyen Tester",
            "card_number": card_number,
            "card_expiry": "12/30",
            "card_cvv": "123",
            "special_instructions": special_instructions,
        }
        if fulfillment_type == "instant":
            form["pickup_date"] = ""
            form["pickup_time"] = ""
        return form

    def _place_order(self, form_data: dict[str, str] | None = None) -> str:
        self._seed_cart()
        response = self.client.post("/checkout", data=form_data or self._valid_checkout_form(), follow_redirects=False)
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
            self.assertEqual(order.payment_status, "Succeeded")
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

    def test_payment_failure_then_retry_success_persists_attempt_log(self):
        self._seed_cart()
        declined = self._valid_checkout_form(card_number="4000 0000 0000 0002")

        failed = self.client.post("/checkout", data=declined)
        self.assertEqual(failed.status_code, 402)
        self.assertIn("configured to decline", failed.get_data(as_text=True))

        with self.app.app_context():
            attempts = PaymentAttempt.query.all()
            self.assertEqual(len(attempts), 1)
            self.assertEqual(attempts[0].status, "Failed")

        succeeded = self.client.post("/checkout", data=self._valid_checkout_form(), follow_redirects=False)
        self.assertEqual(succeeded.status_code, 302)
        order_number = parse_qs(urlparse(succeeded.headers["Location"]).query)["order"][0]

        with self.app.app_context():
            order = Order.query.filter_by(order_number=order_number).first()
            self.assertIsNotNone(order)
            self.assertEqual(len(order.payment_attempts), 2)
            statuses = {attempt.status for attempt in order.payment_attempts}
            self.assertEqual(statuses, {"Failed", "Succeeded"})

        detail = self.client.get(f"/api/orders/{order_number}").get_json()
        self.assertEqual(detail["payment_attempt_count"], 2)

    def test_order_filters_detail_view_and_status_patch(self):
        first_order = self._place_order(self._valid_checkout_form(days_ahead=1))
        second_order = self._place_order(self._valid_checkout_form(days_ahead=2, special_instructions="No coriander, please."))

        update = self.client.patch(
            f"/api/orders/{first_order}/status",
            json={"status": "Preparing", "kitchen_notes": "Broth is on the stove."},
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.get_json()["order_status"], "Preparing")

        filtered_page = self.client.get("/orders?status=Preparing")
        self.assertEqual(filtered_page.status_code, 200)
        html = filtered_page.get_data(as_text=True)
        self.assertIn(first_order, html)
        self.assertNotIn(second_order, html)

        filtered_api = self.client.get("/api/orders?status=Preparing")
        self.assertEqual(filtered_api.status_code, 200)
        payload = filtered_api.get_json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["orders"][0]["order_number"], first_order)

        detail_page = self.client.get(f"/orders/{first_order}")
        self.assertEqual(detail_page.status_code, 200)
        detail_html = detail_page.get_data(as_text=True)
        self.assertIn("Transaction log", detail_html)
        self.assertIn(first_order, detail_html)

    def test_receipt_qr_and_reorder_prefill_work(self):
        order_number = self._place_order(self._valid_checkout_form(special_instructions="Sauce on the side."))

        qr = self.client.get(f"/orders/{order_number}/qr.png")
        self.assertEqual(qr.status_code, 200)
        self.assertEqual(qr.mimetype, "image/png")
        self.assertTrue(qr.data.startswith(b"\x89PNG"))

        reorder = self.client.post(f"/orders/{order_number}/reorder", follow_redirects=False)
        self.assertEqual(reorder.status_code, 302)
        checkout = self.client.get("/checkout")
        self.assertEqual(checkout.status_code, 200)
        html = checkout.get_data(as_text=True)
        self.assertIn("Sauce on the side.", html)
        self.assertIn("Nguyen Tester", html)

    def test_pickup_slot_capacity_blocks_overbooked_time(self):
        self.app.config["PICKUP_SLOT_CAPACITY"] = 1
        order_form = self._valid_checkout_form(days_ahead=1)
        self._place_order(order_form)

        self._seed_cart()
        blocked = self.client.post("/checkout", data=order_form)
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("pickup slot is unavailable", blocked.get_data(as_text=True).lower())

    def test_instant_order_assigns_queue_number_and_eta(self):
        order_number = self._place_order(self._valid_checkout_form(fulfillment_type="instant"))

        with self.app.app_context():
            order = Order.query.filter_by(order_number=order_number).first()
            self.assertIsNotNone(order)
            self.assertEqual(order.fulfillment_type, "instant")
            self.assertEqual(order.queue_number, 1)
            self.assertIsNotNone(order.quoted_wait_minutes)
            self.assertGreater(order.quoted_wait_minutes, 0)
            self.assertIsNotNone(order.counter_label)

        detail = self.client.get(f"/api/orders/{order_number}")
        self.assertEqual(detail.status_code, 200)
        payload = detail.get_json()
        self.assertTrue(payload["is_instant"])
        self.assertEqual(payload["queue_display"], "#001")
        self.assertIn("Instant counter pickup", payload["fulfillment_label"])

    def test_instant_queue_number_increments_by_order(self):
        first = self._place_order(self._valid_checkout_form(fulfillment_type="instant"))
        second = self._place_order(self._valid_checkout_form(fulfillment_type="instant"))

        with self.app.app_context():
            first_order = Order.query.filter_by(order_number=first).first()
            second_order = Order.query.filter_by(order_number=second).first()
            self.assertIsNotNone(first_order)
            self.assertIsNotNone(second_order)
            self.assertEqual(first_order.queue_number, 1)
            self.assertEqual(second_order.queue_number, 2)

    def test_instant_queue_capacity_blocks_new_order(self):
        self.app.config["INSTANT_ORDERING_MAX_ACTIVE_ORDERS"] = 1
        self._place_order(self._valid_checkout_form(fulfillment_type="instant"))

        self._seed_cart()
        blocked = self.client.post("/checkout", data=self._valid_checkout_form(fulfillment_type="instant"))
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("instant queue is full", blocked.get_data(as_text=True).lower())


if __name__ == "__main__":
    unittest.main()
