import tempfile
import unittest
from pathlib import Path

from app import create_app
from models import db


class TestStructuredApiErrors(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "api-errors-test.sqlite"
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
                "OPENAI_API_KEY": "",
            }
        )
        self.client = self.app.test_client()
        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def assert_api_error(self, response, *, status: int, code: str, message: str) -> dict:
        self.assertEqual(response.status_code, status)
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["error"], message)
        self.assertEqual(payload["code"], code)
        self.assertEqual(payload["status"], status)
        return payload

    def test_cart_api_invalid_quantity_has_structured_error(self):
        response = self.client.post(
            "/api/cart/items",
            json={"item_id": "pho-noodle-soup__raw-beef-pho", "quantity": "many"},
        )

        self.assert_api_error(
            response,
            status=400,
            code="invalid_quantity",
            message="quantity must be a whole number",
        )

    def test_missing_api_resource_uses_json_error_handler(self):
        response = self.client.get("/api/orders/MCQ-NOT-FOUND")

        self.assert_api_error(
            response,
            status=404,
            code="not_found",
            message="The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.",
        )

    def test_admin_api_forbidden_has_structured_error(self):
        response = self.client.patch("/api/orders/MCQ-NOT-FOUND/status", json={"status": "Preparing"})

        payload = self.assert_api_error(
            response,
            status=403,
            code="admin_required",
            message="admin access required",
        )
        self.assertIn("login_url", payload)

    def test_support_chat_missing_message_has_structured_error(self):
        response = self.client.post("/api/support-chat", json={"message": ""})

        self.assert_api_error(
            response,
            status=400,
            code="missing_message",
            message="message is required",
        )

    def test_non_api_404_keeps_html_response(self):
        response = self.client.get("/missing-page")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.is_json)


if __name__ == "__main__":
    unittest.main()
