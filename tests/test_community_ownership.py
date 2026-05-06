import tempfile
import unittest
from pathlib import Path

from app import create_app
from models import CommunityPost, db


class TestCommunityPostOwnership(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "community-ownership-test.sqlite"
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

    def _login(self, email: str, name: str = "Community Owner") -> None:
        with self.client.session_transaction() as session:
            session["auth_user"] = {"name": name, "email": email, "role": "customer"}

    def _create_post(self) -> int:
        self._login("owner@example.com", "Owner Member")
        response = self.client.post(
            "/community/posts",
            data={
                "author_name": "Owner Member",
                "post_type": "meal_review",
                "meal_name": "Pho Bo",
                "caption": "Original caption.",
                "order_number": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            post = CommunityPost.query.first()
            self.assertIsNotNone(post)
            return post.id

    def test_owner_can_edit_own_post_via_api(self):
        post_id = self._create_post()

        response = self.client.patch(
            f"/api/community/posts/{post_id}",
            json={
                "author_name": "Owner Member",
                "post_type": "pickup_tip",
                "meal_name": "Banh Mi",
                "caption": "Updated caption.",
                "tip": "Ask for extra herbs.",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["meal"], "Banh Mi")
        self.assertEqual(payload["caption"], "Updated caption.")
        self.assertTrue(payload["viewer_can_edit"])
        with self.app.app_context():
            post = db.session.get(CommunityPost, post_id)
            self.assertEqual(post.meal_name, "Banh Mi")
            self.assertEqual(post.tip, "Ask for extra herbs.")

    def test_non_owner_cannot_edit_post(self):
        post_id = self._create_post()
        self._login("other@example.com", "Other Member")

        response = self.client.patch(
            f"/api/community/posts/{post_id}",
            json={
                "author_name": "Other Member",
                "post_type": "meal_review",
                "meal_name": "Changed Dish",
                "caption": "Should not save.",
            },
        )

        self.assertEqual(response.status_code, 403)
        payload = response.get_json()
        self.assertEqual(payload["code"], "community_post_forbidden")
        with self.app.app_context():
            post = db.session.get(CommunityPost, post_id)
            self.assertEqual(post.meal_name, "Pho Bo")
            self.assertEqual(post.caption, "Original caption.")

    def test_non_owner_cannot_delete_post(self):
        post_id = self._create_post()
        self._login("other@example.com", "Other Member")

        response = self.client.delete(f"/api/community/posts/{post_id}")

        self.assertEqual(response.status_code, 403)
        payload = response.get_json()
        self.assertEqual(payload["code"], "community_post_forbidden")
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(CommunityPost, post_id))

    def test_owner_can_delete_own_post(self):
        post_id = self._create_post()

        response = self.client.delete(f"/api/community/posts/{post_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"deleted": True, "post_id": post_id})
        with self.app.app_context():
            self.assertIsNone(db.session.get(CommunityPost, post_id))

    def test_form_delete_for_non_owner_returns_forbidden(self):
        post_id = self._create_post()
        self._login("other@example.com", "Other Member")

        response = self.client.post(f"/community/posts/{post_id}/delete", follow_redirects=False)

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
