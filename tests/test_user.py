import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import create_app
from models import db


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
