/**
 * McqCart: thin client wrapper around /api/cart/*.
 * Cart state is stored server-side in Flask session.
 */
(function () {
  async function parseJsonResponse(response) {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const msg = data.error || response.statusText || "Request failed";
      throw new Error(msg);
    }
    return data;
  }

  window.McqCart = {
    async get() {
      const r = await fetch("/api/cart/");
      return parseJsonResponse(r);
    },

    async add(itemId, quantity) {
      const r = await fetch("/api/cart/items", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ item_id: itemId, quantity: quantity ?? 1 }),
      });
      return parseJsonResponse(r);
    },

    async setQuantity(itemId, quantity) {
      const r = await fetch(`/api/cart/items/${encodeURIComponent(itemId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ quantity }),
      });
      return parseJsonResponse(r);
    },

    async remove(itemId) {
      const r = await fetch(`/api/cart/items/${encodeURIComponent(itemId)}`, {
        method: "DELETE",
        headers: { Accept: "application/json" },
      });
      return parseJsonResponse(r);
    },

    async clear() {
      const r = await fetch("/api/cart/clear", { method: "POST", headers: { Accept: "application/json" } });
      return parseJsonResponse(r);
    },
  };
})();

