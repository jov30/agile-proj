import tempfile
import unittest
from pathlib import Path

from app import create_app
from models import Voucher, db


class TestAdminVouchers(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "vouchers-test.sqlite"
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

    def _login_admin(self) -> None:
        response = self.client.post(
            "/login",
            data={
                "email": self.app.config["ADMIN_EMAIL"],
                "password": self.app.config["ADMIN_PASSWORD"],
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

    def test_voucher_page_requires_admin(self):
        response = self.client.get("/admin/vouchers", follow_redirects=False)
        self.assertIn(response.status_code, {302, 401, 403})

    def test_voucher_list_renders_for_admin(self):
        self._login_admin()
        response = self.client.get("/admin/vouchers")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Voucher", response.get_data())

    def test_admin_can_create_voucher(self):
        self._login_admin()
        response = self.client.post(
            "/admin/vouchers",
            data={
                "action": "create",
                "value": "20",
                "label": "Birthday Gift Voucher",
                "subtitle": "For a lucky customer",
                "description": "Twenty dollars to spend on banh mi.",
                "terms": "One time use only.",
                "included_items": "2 banh mi serves approx.",
                "expires_at": "31 Dec 2026",
                "footer_note": "Authorised by MCQ.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            vouchers = Voucher.query.all()
            self.assertEqual(len(vouchers), 1)
            voucher = vouchers[0]
            self.assertEqual(voucher.value_cents, 2000)
            self.assertEqual(voucher.label, "Birthday Gift Voucher")
            self.assertTrue(voucher.code.startswith("MCQ-"))

    def test_invalid_value_falls_back_to_default_dollars(self):
        self._login_admin()
        self.client.post(
            "/admin/vouchers",
            data={
                "action": "create",
                "value": "not-a-number",
                "label": "Fallback voucher",
            },
        )
        with self.app.app_context():
            voucher = Voucher.query.first()
            self.assertIsNotNone(voucher)
            self.assertEqual(voucher.value_cents, 1000)

    def test_admin_can_update_existing_voucher(self):
        self._login_admin()
        self.client.post(
            "/admin/vouchers",
            data={
                "action": "create",
                "value": "30",
                "label": "Initial label",
            },
        )
        with self.app.app_context():
            voucher = Voucher.query.first()
            voucher_id = voucher.id
            original_code = voucher.code

        self.client.post(
            "/admin/vouchers",
            data={
                "action": "update",
                "voucher_id": str(voucher_id),
                "value": "50",
                "label": "Updated label",
                "subtitle": "Refreshed subtitle",
            },
        )
        with self.app.app_context():
            voucher = Voucher.query.get(voucher_id)
            self.assertEqual(voucher.value_cents, 5000)
            self.assertEqual(voucher.label, "Updated label")
            self.assertEqual(voucher.subtitle, "Refreshed subtitle")
            self.assertEqual(voucher.code, original_code)
            self.assertEqual(Voucher.query.count(), 1)

    def test_each_voucher_gets_unique_code(self):
        self._login_admin()
        for index in range(3):
            self.client.post(
                "/admin/vouchers",
                data={
                    "action": "create",
                    "value": "20",
                    "label": f"Voucher {index}",
                },
            )
        with self.app.app_context():
            codes = [voucher.code for voucher in Voucher.query.all()]
            self.assertEqual(len(codes), 3)
            self.assertEqual(len(set(codes)), 3)
            for code in codes:
                self.assertTrue(code.startswith("MCQ-"))


if __name__ == "__main__":
    unittest.main()
