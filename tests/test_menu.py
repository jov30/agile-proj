import unittest

from app import app


class TestMenuAndCart(unittest.TestCase):
    def setUp(self) -> None:
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_api_menu_contains_items_with_ids(self):
        resp = self.client.get("/api/menu")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, dict)
        self.assertIn("categories", data)

        categories = data["categories"]
        self.assertTrue(len(categories) > 0)

        first_cat = categories[0]
        items = first_cat.get("items") or []
        self.assertTrue(len(items) > 0)
        first_item = items[0]
        self.assertIn("id", first_item)
        self.assertIn("name", first_item)

    def test_cart_lifecycle_add_update_remove(self):
        menu = self.client.get("/api/menu").get_json()
        first_item = menu["categories"][0]["items"][0]
        item_id = first_item["id"]

        # Empty cart
        resp = self.client.get("/api/cart/")
        self.assertEqual(resp.status_code, 200)
        cart = resp.get_json()
        self.assertEqual(cart["total_cents"], 0)
        self.assertEqual(len(cart["lines"]), 0)

        # Add
        resp = self.client.post("/api/cart/items", json={"item_id": item_id, "quantity": 2})
        self.assertEqual(resp.status_code, 200)
        cart = resp.get_json()
        self.assertEqual(len(cart["lines"]), 1)
        self.assertEqual(cart["lines"][0]["item_id"], item_id)
        self.assertEqual(cart["lines"][0]["quantity"], 2)
        self.assertGreater(cart["total_cents"], 0)

        # Update quantity
        resp = self.client.patch(f"/api/cart/items/{item_id}", json={"quantity": 1})
        self.assertEqual(resp.status_code, 200)
        cart = resp.get_json()
        self.assertEqual(cart["lines"][0]["quantity"], 1)

        # Remove
        resp = self.client.delete(f"/api/cart/items/{item_id}")
        self.assertEqual(resp.status_code, 200)
        cart = resp.get_json()
        self.assertEqual(len(cart["lines"]), 0)
        self.assertEqual(cart["total_cents"], 0)

    def test_menu_item_detail_route(self):
        menu = self.client.get("/api/menu").get_json()
        first_item = menu["categories"][0]["items"][0]
        item_id = first_item["id"]

        resp = self.client.get(f"/menu/item/{item_id}")
        self.assertEqual(resp.status_code, 200)
        text = resp.get_data(as_text=True)
        self.assertIn(first_item["name"], text)

        resp = self.client.get("/menu/item/bad-id")
        self.assertEqual(resp.status_code, 404)

    def test_cart_page_renders(self):
        resp = self.client.get("/cart")
        self.assertEqual(resp.status_code, 200)
        text = resp.get_data(as_text=True)
        self.assertIn('id="cart-root"', text)


if __name__ == "__main__":
    unittest.main()

