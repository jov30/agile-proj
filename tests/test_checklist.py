import tempfile
import unittest
from datetime import date
from pathlib import Path

from app import create_app
from models import (
    ChecklistAuditLog,
    ChecklistSession,
    ChecklistTask,
    TemperatureReading,
    TemperatureSession,
    db,
)


class TestChecklistOperations(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "checklist-test.sqlite"
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
        )
        self.assertEqual(response.status_code, 302)

    def test_checklist_home_requires_admin(self):
        response = self.client.get("/admin/checklist/", follow_redirects=False)
        self.assertIn(response.status_code, {302, 401, 403})

    def test_checklist_home_renders_for_admin(self):
        self._login_admin()
        response = self.client.get("/admin/checklist/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Checklist", response.get_data())

    def test_checklist_sheet_form_loads(self):
        self._login_admin()
        response = self.client.get("/admin/checklist/sheet/take_order?section=opening")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cashier", response.get_data())

    def test_unknown_checklist_type_redirects_home(self):
        self._login_admin()
        response = self.client.get(
            "/admin/checklist/sheet/does_not_exist",
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/checklist", response.headers["Location"])

    def test_save_checklist_creates_session_tasks_and_audit_log(self):
        self._login_admin()
        today_iso = date.today().isoformat()
        response = self.client.post(
            "/admin/checklist/sheet/take_order/save",
            data={
                "date": today_iso,
                "section": "opening",
                "responsible": "Thang Nguyen",
                "submitted_by": "Thang Nguyen",
                "general_done_by": "Thang Nguyen",
                "manager_submit": "Khoi",
                "general_note": "Opening shift complete.",
                "done_0": "on",
                "done_1": "on",
                "note_0": "Cash counted.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            session_row = ChecklistSession.query.filter_by(
                checklist_type="take_order",
                section="opening",
                session_date=date.today(),
            ).first()
            self.assertIsNotNone(session_row)
            self.assertEqual(session_row.submitted_by, "Thang Nguyen")
            tasks = ChecklistTask.query.filter_by(session_id=session_row.id).all()
            self.assertGreater(len(tasks), 0)
            done_tasks = [task for task in tasks if task.done]
            self.assertEqual(len(done_tasks), 2)
            audit = ChecklistAuditLog.query.filter_by(action="SAVE_CHECKLIST").all()
            self.assertEqual(len(audit), 1)

    def test_manager_can_verify_checklist_session(self):
        self._login_admin()
        today_iso = date.today().isoformat()
        self.client.post(
            "/admin/checklist/sheet/take_order/save",
            data={
                "date": today_iso,
                "section": "opening",
                "submitted_by": "Thang Nguyen",
            },
        )

        with self.app.app_context():
            session_row = ChecklistSession.query.first()
            session_id = session_row.id
            self.assertFalse(session_row.verified)

        response = self.client.post(
            f"/admin/checklist/sheet/verify/{session_id}",
            data={
                "verified_by": "Khoi",
                "overall_result": "pass",
                "manager_notes": "Looks good.",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            session_row = ChecklistSession.query.get(session_id)
            self.assertTrue(session_row.verified)
            self.assertEqual(session_row.verified_by, "Khoi")
            self.assertEqual(session_row.overall_result, "pass")
            verify_audit = ChecklistAuditLog.query.filter_by(action="VERIFY").first()
            self.assertIsNotNone(verify_audit)

    def test_temperature_save_persists_readings(self):
        self._login_admin()
        today_iso = date.today().isoformat()
        response = self.client.post(
            "/admin/checklist/temperature/banh_mi/save",
            data={
                "date": today_iso,
                "recorded_by": "Thang Nguyen",
                "checked_by": "Khoi",
                "notes": "Temperatures look healthy.",
                "c1_time_0": "10:00",
                "c1_temp_0": "4.2",
                "c2_time_0": "12:00",
                "c2_temp_0": "4.5",
                "discarded_0": "N",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            session_row = TemperatureSession.query.filter_by(
                record_type="banh_mi",
                session_date=date.today(),
            ).first()
            self.assertIsNotNone(session_row)
            self.assertEqual(session_row.recorded_by, "Thang Nguyen")
            readings = TemperatureReading.query.filter_by(session_id=session_row.id).all()
            self.assertGreater(len(readings), 0)
            first_reading = next(
                (r for r in readings if r.food_order == 0),
                None,
            )
            self.assertIsNotNone(first_reading)
            self.assertEqual(first_reading.c1_temp, 4.2)
            self.assertEqual(first_reading.c2_temp, 4.5)


if __name__ == "__main__":
    unittest.main()
