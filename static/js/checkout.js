(function () {
  const root = document.querySelector("[data-checkout-root]");
  if (!root) return;

  const windowsNode = document.getElementById("pickup-windows-data");
  const pickupWindows = windowsNode ? JSON.parse(windowsNode.textContent || "[]") : [];
  const dateSelect = document.getElementById("pickup_date");
  const timeSelect = document.getElementById("pickup_time");
  const paymentInputs = document.querySelectorAll('input[name="payment_method"]');
  const cardFields = document.getElementById("card-fields");
  const cardInputs = cardFields ? cardFields.querySelectorAll("input") : [];
  const cardNumber = document.getElementById("card_number");
  const cardExpiry = document.getElementById("card_expiry");
  const cardCvv = document.getElementById("card_cvv");
  const pickupPreviewTitle = document.getElementById("pickup-preview-title");
  const pickupPreviewCopy = document.getElementById("pickup-preview-copy");
  const paymentPreviewTitle = document.getElementById("payment-preview-title");
  const paymentPreviewCopy = document.getElementById("payment-preview-copy");

  function formatCardNumber(value) {
    return value.replace(/\D/g, "").slice(0, 19).replace(/(.{4})/g, "$1 ").trim();
  }

  function formatExpiry(value) {
    const digits = value.replace(/\D/g, "").slice(0, 4);
    if (digits.length <= 2) return digits;
    return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  }

  function formatCvv(value) {
    return value.replace(/\D/g, "").slice(0, 4);
  }

  function selectedPaymentInput() {
    return Array.from(paymentInputs).find((input) => input.checked) || null;
  }

  function selectedWindow() {
    return pickupWindows.find((window) => window.date === dateSelect.value) || null;
  }

  function renderTimeOptions() {
    if (!dateSelect || !timeSelect) return;

    const previous = timeSelect.value;
    const window = selectedWindow();
    const slots = window ? window.slots : [];
    timeSelect.innerHTML = "";

    slots.forEach((slot, index) => {
      const option = document.createElement("option");
      option.value = slot.value;
      option.textContent = slot.label;
      if (slot.value === previous || (!previous && index === 0)) {
        option.selected = true;
      }
      timeSelect.appendChild(option);
    });
  }

  function updatePickupPreview() {
    if (!dateSelect || !timeSelect || !pickupPreviewTitle || !pickupPreviewCopy) return;

    const window = selectedWindow();
    const selectedOption = timeSelect.options[timeSelect.selectedIndex];
    pickupPreviewTitle.textContent = window ? window.label : "Choose a pickup day";
    pickupPreviewCopy.textContent = `Selected pickup time: ${selectedOption ? selectedOption.textContent : "Choose a time"}`;
  }

  function updatePaymentPreview() {
    const input = selectedPaymentInput();
    if (!input || !paymentPreviewTitle || !paymentPreviewCopy) return;

    paymentPreviewTitle.textContent = input.dataset.paymentLabel || "Payment method";
    if (input.dataset.requiresCard === "true") {
      paymentPreviewCopy.textContent = "A simulated approval reference and masked last four digits are attached to the order.";
    } else {
      paymentPreviewCopy.textContent = "The order is marked as paid with a simulated wallet approval reference.";
    }
  }

  function updateCardFields() {
    const input = selectedPaymentInput();
    const requiresCard = input && input.dataset.requiresCard === "true";

    if (!cardFields) return;
    cardFields.hidden = !requiresCard;
    cardInputs.forEach((field) => {
      field.disabled = !requiresCard;
    });
  }

  function scrollToActiveSection() {
    const entryStep = root.dataset.entryStep;
    if (entryStep === "payment") {
      document.getElementById("checkout-payment")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (entryStep === "pickup") {
      document.getElementById("checkout-pickup")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  paymentInputs.forEach((input) => {
    input.addEventListener("change", () => {
      updateCardFields();
      updatePaymentPreview();
    });
  });

  if (dateSelect) {
    dateSelect.addEventListener("change", () => {
      renderTimeOptions();
      updatePickupPreview();
    });
  }

  if (timeSelect) {
    timeSelect.addEventListener("change", updatePickupPreview);
  }

  if (cardNumber) {
    cardNumber.addEventListener("input", () => {
      cardNumber.value = formatCardNumber(cardNumber.value);
    });
  }

  if (cardExpiry) {
    cardExpiry.addEventListener("input", () => {
      cardExpiry.value = formatExpiry(cardExpiry.value);
    });
  }

  if (cardCvv) {
    cardCvv.addEventListener("input", () => {
      cardCvv.value = formatCvv(cardCvv.value);
    });
  }

  renderTimeOptions();
  updateCardFields();
  updatePickupPreview();
  updatePaymentPreview();
  window.setTimeout(scrollToActiveSection, 120);
})();
