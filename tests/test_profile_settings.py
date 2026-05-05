from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import create_app
from models import User, db


class TestProfileSettings(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = Path(self.tmpdir.name) / "settings-test.sqlite"
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "PICKUP_OPEN_HOUR": 0,
            "PICKUP_OPEN_MINUTE": 0,
            "PICKUP_CLOSE_HOUR": 23,
            "PICKUP_CLOSE_MINUTE": 59,
        })
        self.client = self.app.test_client()

        with self.app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(User(
                name="Linh Nguyen",
                email="linh@test.com",
                password_hash="x",
                role="customer",
            ))
            db.session.commit()

        with self.client.session_transaction() as sess:
            sess["auth_user"] = {
                "name": "Linh Nguyen",
                "email": "linh@test.com",
                "role": "customer",
            }

    def tearDown(self) -> None:
        with self.app.app_context():
            db.engine.dispose()
        self.tmpdir.cleanup()

    def _valid_form(self, **overrides) -> dict:
        base = {
            "name": "Linh Nguyen",
            "username": "linh.nguyen",
            "phone": "0412 345 678",
            "date_of_birth": "1995-06-15",
            "dietary_preferences": "No restrictions",
            "default_pickup_mode": "scheduled",
            "notification_email": "on",
            "notification_sms": "",
            "marketing_opt_in": "",
        }
        base.update(overrides)
        return base

    # ── Rendering ────────────────────────────────────────────────────────

    def test_settings_page_renders_for_logged_in_user(self):
        response = self.client.get("/profile/settings")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Profile Settings", html)
        self.assertIn("Linh Nguyen", html)
        self.assertIn("linh@test.com", html)

    def test_settings_page_redirects_when_not_logged_in(self):
        with self.client.session_transaction() as sess:
            sess.pop("auth_user", None)
        response = self.client.get("/profile/settings", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_settings_page_shows_existing_field_values(self):
        with self.app.app_context():
            user = User.query.filter_by(email="linh@test.com").first()
            user.phone = "0412 999 888"
            user.date_of_birth = date(1995, 6, 15)
            user.dietary_preferences = "Vegetarian"
            user.default_pickup_mode = "instant"
            db.session.commit()

        response = self.client.get("/profile/settings")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("0412 999 888", html)
        self.assertIn("1995-06-15", html)
        self.assertIn("Vegetarian", html)

    # ── Saving ───────────────────────────────────────────────────────────

    def test_valid_form_saves_all_fields(self):
        response = self.client.post("/profile/settings", data=self._valid_form(
            username="linh.test",
            phone="0400 111 222",
            date_of_birth="1993-03-20",
            dietary_preferences="Halal",
            default_pickup_mode="instant",
            notification_email="on",
            notification_sms="on",
            marketing_opt_in="on",
        ))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Profile updated successfully", response.get_data(as_text=True))

        with self.app.app_context():
            user = User.query.filter_by(email="linh@test.com").first()
            self.assertEqual(user.username, "linh.test")
            self.assertEqual(user.phone, "0400 111 222")
            self.assertEqual(user.date_of_birth, date(1993, 3, 20))
            self.assertEqual(user.dietary_preferences, "Halal")
            self.assertEqual(user.default_pickup_mode, "instant")
            self.assertTrue(user.notification_email)
            self.assertTrue(user.notification_sms)
            self.assertTrue(user.marketing_opt_in)

    def test_name_change_updates_session(self):
        self.client.post("/profile/settings", data=self._valid_form(name="Linh T. Nguyen"))
        with self.client.session_transaction() as sess:
            self.assertEqual(sess["auth_user"]["name"], "Linh T. Nguyen")

    def test_unchecked_toggles_save_as_false(self):
        # Post without any checkbox keys — they should be False
        self.client.post("/profile/settings", data=self._valid_form(
            notification_email="",
            notification_sms="",
            marketing_opt_in="",
        ))
        with self.app.app_context():
            user = User.query.filter_by(email="linh@test.com").first()
            self.assertFalse(user.notification_email)
            self.assertFalse(user.notification_sms)
            self.assertFalse(user.marketing_opt_in)

    def test_optional_fields_can_be_cleared(self):
        # Set values first
        with self.app.app_context():
            user = User.query.filter_by(email="linh@test.com").first()
            user.username = "old_handle"
            user.phone = "0400 000 000"
            user.date_of_birth = date(1990, 1, 1)
            db.session.commit()

        self.client.post("/profile/settings", data=self._valid_form(
            username="", phone="", date_of_birth=""
        ))
        with self.app.app_context():
            user = User.query.filter_by(email="linh@test.com").first()
            self.assertIsNone(user.username)
            self.assertIsNone(user.phone)
            self.assertIsNone(user.date_of_birth)

    # ── Validation ───────────────────────────────────────────────────────

    def test_empty_name_is_rejected(self):
        response = self.client.post("/profile/settings", data=self._valid_form(name="x"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Full name must be at least 2 characters", response.get_data(as_text=True))

    def test_invalid_dob_string_is_rejected(self):
        response = self.client.post("/profile/settings", data=self._valid_form(date_of_birth="not-a-date"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid date of birth", response.get_data(as_text=True))

    def test_underage_dob_is_rejected(self):
        underage = (date.today() - timedelta(days=365 * 10)).isoformat()
        response = self.client.post("/profile/settings", data=self._valid_form(date_of_birth=underage))
        self.assertEqual(response.status_code, 400)
        self.assertIn("at least 13", response.get_data(as_text=True))

    def test_invalid_username_characters_rejected(self):
        response = self.client.post("/profile/settings", data=self._valid_form(username="bad name!"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Username may only contain", response.get_data(as_text=True))

    def test_short_username_rejected(self):
        response = self.client.post("/profile/settings", data=self._valid_form(username="ab"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("at least 3 characters", response.get_data(as_text=True))

    def test_duplicate_username_rejected(self):
        # Create a second user with a taken username
        with self.app.app_context():
            db.session.add(User(
                name="Minh Tran",
                email="minh@test.com",
                password_hash="x",
                role="customer",
                username="taken_handle",
            ))
            db.session.commit()

        response = self.client.post("/profile/settings", data=self._valid_form(username="taken_handle"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("already taken", response.get_data(as_text=True))

    def test_same_username_as_own_does_not_conflict(self):
        with self.app.app_context():
            user = User.query.filter_by(email="linh@test.com").first()
            user.username = "my_handle"
            db.session.commit()

        response = self.client.post("/profile/settings", data=self._valid_form(username="my_handle"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Profile updated successfully", response.get_data(as_text=True))

    def test_invalid_phone_rejected(self):
        response = self.client.post("/profile/settings", data=self._valid_form(phone="123"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid phone number", response.get_data(as_text=True))

    def test_invalid_pickup_mode_rejected(self):
        response = self.client.post("/profile/settings", data=self._valid_form(default_pickup_mode="walk_in"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("valid default pickup mode", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()