import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from models import db


class TestAdminMenuManagement(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmpdir.name)
        db_path = tmp_path / "menu-admin-test.sqlite"

        original_menu = Path(__file__).resolve().parent.parent / "static" / "data" / "menu.json"
        self.menu_path = tmp_path / "menu.json"
        shutil.copy(original_menu, self.menu_path)

        self._menu_patch = patch("routes.admin._menu_path", return_value=self.menu_path)
        self._menu_patch.start()

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
        self._menu_patch.stop()
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

    def _read_menu(self) -> dict:
        with self.menu_path.open(encoding="utf-8") as f:
            return json.load(f)

    def _first_category(self) -> dict:
        return self._read_menu()["categories"][0]

    def test_menu_page_requires_admin(self):
        response = self.client.get("/admin/menu", follow_redirects=False)
        self.assertIn(response.status_code, {302, 401, 403})

    def test_menu_page_renders_for_admin(self):
        self._login_admin()
        response = self.client.get("/admin/menu")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Menu", response.get_data())

    def test_admin_can_add_menu_item(self):
        self._login_admin()
        category_id = self._first_category()["id"]
        before = len(self._first_category()["items"])

        response = self.client.post(
            "/admin/menu",
            data={
                "action": "add",
                "category_id": category_id,
                "name": "Test Pho Special",
                "price": "$15",
                "summary": "Test summary for new dish.",
                "image": "images/menu/test.jpg",
                "ingredients": "Rice noodles, Beef, Herbs",
                "available": "on",
            },
        )
        self.assertEqual(response.status_code, 200)

        after = len(self._first_category()["items"])
        self.assertEqual(after, before + 1)

        new_item = self._first_category()["items"][-1]
        self.assertEqual(new_item["name"], "Test Pho Special")
        self.assertEqual(new_item["price"], "$15")
        self.assertTrue(new_item["available"])
        ingredients_section = next(
            (
                section
                for section in new_item["sections"]
                if str(section.get("label", "")).lower() == "ingredients"
            ),
            None,
        )
        self.assertIsNotNone(ingredients_section)
        self.assertIn("Rice noodles", ingredients_section["items"])

    def test_admin_can_edit_existing_item(self):
        self._login_admin()
        category_id = self._first_category()["id"]
        self.client.post(
            "/admin/menu",
            data={
                "action": "add",
                "category_id": category_id,
                "name": "Editable Item",
                "price": "$10",
                "ingredients": "Original ingredient",
                "available": "on",
            },
        )

        from menu_catalog import load_enriched_menu

        enriched = load_enriched_menu(self.menu_path)
        target_id = enriched["categories"][0]["items"][-1]["id"]

        self.client.post(
            "/admin/menu",
            data={
                "action": "edit",
                "item_id": target_id,
                "name": "Edited Item Name",
                "price": "$12",
                "summary": "Updated summary.",
                "ingredients": "New ingredient",
            },
        )

        edited = self._first_category()["items"][-1]
        self.assertEqual(edited["name"], "Edited Item Name")
        self.assertEqual(edited["price"], "$12")
        self.assertFalse(edited["available"])
        ingredients_section = next(
            (
                section
                for section in edited["sections"]
                if str(section.get("label", "")).lower() == "ingredients"
            ),
            None,
        )
        self.assertIn("New ingredient", ingredients_section["items"])
        self.assertNotIn("Original ingredient", ingredients_section["items"])

    def test_admin_can_delete_menu_item(self):
        self._login_admin()
        category_id = self._first_category()["id"]
        self.client.post(
            "/admin/menu",
            data={
                "action": "add",
                "category_id": category_id,
                "name": "Doomed Item",
                "price": "$8",
                "ingredients": "filler",
                "available": "on",
            },
        )
        from menu_catalog import load_enriched_menu

        enriched = load_enriched_menu(self.menu_path)
        names_before = [item["name"] for item in enriched["categories"][0]["items"]]
        self.assertIn("Doomed Item", names_before)
        target_id = next(
            item["id"]
            for item in enriched["categories"][0]["items"]
            if item["name"] == "Doomed Item"
        )

        self.client.post(
            "/admin/menu",
            data={"action": "delete", "item_id": target_id},
        )
        names_after = [item["name"] for item in self._first_category()["items"]]
        self.assertNotIn("Doomed Item", names_after)


if __name__ == "__main__":
    unittest.main()
