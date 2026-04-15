import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from app import create_app
from models import Order, OrderLineItem, db


class TestSupportChat(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "support-test.sqlite"
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
                "PICKUP_OPEN_HOUR": 0,
                "PICKUP_OPEN_MINUTE": 0,
                "PICKUP_CLOSE_HOUR": 23,
                "PICKUP_CLOSE_MINUTE": 59,
                "OPENAI_API_KEY": "",
            }
        )
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _login_customer(self) -> None:
        with self.client.session_transaction() as session:
            session["auth_user"] = {
                "name": "Lantern Member",
                "email": "member@example.com",
                "role": "customer",
            }

    def _seed_member_order(self, *, total_cents: int = 3350, quantity: int = 2) -> None:
        with self.app.app_context():
            order = Order(
                order_number="MCQ-TEST-1001",
                confirmation_code="AB12CD",
                customer_name="Lantern Member",
                customer_email="member@example.com",
                customer_phone="0412 345 678",
                fulfillment_type="instant",
                pickup_at=datetime.now(ZoneInfo(self.app.config["APP_TIMEZONE"])).replace(tzinfo=None),
                queue_date=None,
                queue_number=3,
                quoted_wait_minutes=18,
                counter_label="Front Pickup Counter",
                payment_method="card",
                payment_status="Succeeded",
                payment_reference="PAY-TEST-1001",
                order_status="Ready for Pickup",
                kitchen_notes="",
                special_instructions="",
                subtotal_cents=total_cents - 150,
                service_fee_cents=150,
                total_cents=total_cents,
            )
            order.line_items.append(
                OrderLineItem(
                    item_id="pho-noodle-soup__raw-beef-pho",
                    item_name="Raw Beef Pho",
                    category_title="Pho Noodle Soup",
                    unit_price_cents=(total_cents - 150) // max(1, quantity),
                    quantity=quantity,
                    line_total_cents=total_cents - 150,
                )
            )
            db.session.add(order)
            db.session.commit()

    def test_support_chat_requires_message(self):
        response = self.client.post("/api/support-chat", json={"message": ""})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "message is required")

    def test_support_chat_falls_back_when_api_key_missing(self):
        response = self.client.post("/api/support-chat", json={"message": "How does instant queue work?"})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["mode"], "fallback")
        self.assertFalse(payload["ai_enabled"])
        self.assertEqual(payload["fallback_reason"], "missing_api_key")
        self.assertIn("Instant queue", payload["reply"])

    def test_chatbox_is_closed_by_default_without_api_key(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="support-dock"', html)
        self.assertNotIn('support-dock is-open', html)
        self.assertIn("Fallback Assistant", html)
        self.assertIn(">Community<", html)

    def test_profile_page_renders_membership_dashboard(self):
        self._login_customer()
        self._seed_member_order(total_cents=100000, quantity=5)

        response = self.client.get("/profile")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("MCQ Membership", html)
        self.assertIn("Lantern Member", html)
        self.assertIn("Points wallet", html)
        self.assertIn("MCQ Community", html)
        self.assertIn("1000 points = $10 voucher", html)
        self.assertIn("/membership/barcode.svg", html)
        self.assertIn("Distinction Member", html)

        barcode = self.client.get("/membership/barcode.svg")
        self.assertEqual(barcode.status_code, 200)
        self.assertEqual(barcode.mimetype, "image/svg+xml")
        self.assertIn("MCQ-", barcode.get_data(as_text=True))

    def test_saved_meals_and_community_pages_render_new_scaffolds(self):
        self._login_customer()
        self._seed_member_order()

        favorites = self.client.get("/favorites")
        self.assertEqual(favorites.status_code, 200)
        favorites_html = favorites.get_data(as_text=True)
        self.assertIn("Saved Meals", favorites_html)
        self.assertIn("Member favourite", favorites_html)

        community = self.client.get("/community")
        self.assertEqual(community.status_code, 200)
        community_html = community.get_data(as_text=True)
        self.assertIn("MCQ Community", community_html)
        self.assertIn("Share Meal Story", community_html)
        self.assertIn("Story composer", community_html)

    @patch("routes.user.requests.post")
    def test_support_chat_uses_openai_when_configured(self, mock_post):
        self.app.config["OPENAI_API_KEY"] = "test-key"

        mock_response = Mock()
        mock_response.json.return_value = {"output_text": "AI says: use the menu, then checkout."}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        response = self.client.post("/api/support-chat", json={"message": "What should I do next?"})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["mode"], "ai")
        self.assertTrue(payload["ai_enabled"])
        self.assertEqual(payload["reply"], "AI says: use the menu, then checkout.")

        self.assertTrue(mock_post.called)
        request_kwargs = mock_post.call_args.kwargs
        self.assertIn("/responses", mock_post.call_args.args[0])
        self.assertEqual(request_kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(request_kwargs["json"]["model"], self.app.config["OPENAI_CHAT_MODEL"])


if __name__ == "__main__":
    unittest.main()
