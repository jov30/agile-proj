(function () {
  const root = document.querySelector("[data-admin-root]");
  if (!root) return;

  function setInlineStatus(card, message, isError) {
    const node = card.querySelector("[data-inline-status]");
    if (!node) return;
    node.textContent = message || "";
    node.classList.toggle("is-error", Boolean(isError));
  }

  async function updateOrderStatus(button) {
    const orderNumber = button.dataset.orderNumber;
    const nextStatus = button.dataset.nextStatus;
    if (!orderNumber || !nextStatus) return;

    const card = button.closest("[data-admin-order]");
    if (!card) return;
    const allButtons = Array.from(card.querySelectorAll(".admin-status-action"));
    allButtons.forEach((item) => {
      item.disabled = true;
    });
    setInlineStatus(card, `Updating status to ${nextStatus}...`, false);

    try {
      const response = await fetch(`/api/orders/${encodeURIComponent(orderNumber)}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      const payload = await response.json();
      if (!response.ok) {
        const message = payload.error || "Could not update order status.";
        throw new Error(message);
      }

      const badge = card.querySelector("[data-order-status]");
      if (badge) {
        badge.textContent = payload.order_status;
      }
      setInlineStatus(card, `Saved. ${payload.order_number} is now ${payload.order_status}.`, false);
      window.setTimeout(() => {
        window.location.reload();
      }, 500);
    } catch (error) {
      setInlineStatus(card, error.message || "Could not update order status.", true);
      allButtons.forEach((item) => {
        item.disabled = false;
      });
    }
  }

  root.querySelectorAll(".admin-status-action").forEach((button) => {
    button.addEventListener("click", () => {
      updateOrderStatus(button);
    });
  });
})();
