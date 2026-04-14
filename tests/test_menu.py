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
        self.assertEqual(cart["line_count"], 1)
        self.assertEqual(cart["item_count"], 2)
        self.assertGreater(cart["service_fee_cents"], 0)
        self.assertEqual(cart["checkout_total_cents"], cart["total_cents"] + cart["service_fee_cents"])

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

        resp = self.client.get(f"/menu/item/{item_id}?fulfillment=scheduled")
        self.assertEqual(resp.status_code, 200)
        text = resp.get_data(as_text=True)
        self.assertIn(first_item["name"], text)
        self.assertIn("/checkout?fulfillment=scheduled", text)
        self.assertIn("/cart?fulfillment=scheduled", text)

        resp = self.client.get("/menu/item/bad-id")
        self.assertEqual(resp.status_code, 404)

    def test_cart_page_renders(self):
        resp = self.client.get("/cart?fulfillment=scheduled")
        self.assertEqual(resp.status_code, 200)
        text = resp.get_data(as_text=True)
        self.assertIn('id="cart-root"', text)
        self.assertIn("Scheduled pickup path", text)

    def test_landing_and_menu_routes_emphasize_real_ordering_paths(self):
        landing = self.client.get("/")
        self.assertEqual(landing.status_code, 200)
        landing_html = landing.get_data(as_text=True)
        self.assertIn("/menu?fulfillment=instant", landing_html)
        self.assertIn("/menu?fulfillment=scheduled", landing_html)
        self.assertNotIn("/favorites", landing_html)

        menu_page = self.client.get("/menu?fulfillment=scheduled")
        self.assertEqual(menu_page.status_code, 200)
        menu_html = menu_page.get_data(as_text=True)
        self.assertIn("/cart?fulfillment=scheduled", menu_html)
        self.assertIn("/checkout?fulfillment=scheduled", menu_html)

    def test_cart_api_rejects_invalid_quantity_payloads(self):
        menu = self.client.get("/api/menu").get_json()
        item_id = menu["categories"][0]["items"][0]["id"]

        add = self.client.post("/api/cart/items", json={"item_id": item_id, "quantity": "abc"})
        self.assertEqual(add.status_code, 400)
        self.assertEqual(add.get_json()["error"], "quantity must be a whole number")

        patch = self.client.patch(f"/api/cart/items/{item_id}", json={"quantity": "abc"})
        self.assertEqual(patch.status_code, 400)
        self.assertEqual(patch.get_json()["error"], "quantity must be a whole number")


if __name__ == "__main__":
    unittest.main()
