(function () {
  const root = document.querySelector("[data-checkout-root]");
  if (!root) return;

  const draftKey = "mcq_checkout_draft_v1";
  const windowsNode = document.getElementById("pickup-windows-data");
  const pickupWindows = windowsNode ? JSON.parse(windowsNode.textContent || "[]") : [];
  const instantQueueNode = document.getElementById("instant-queue-data");
  const instantQueue = instantQueueNode ? JSON.parse(instantQueueNode.textContent || "{}") : {};
  const form = document.getElementById("checkout-form");
  const dateSelect = document.getElementById("pickup_date");
  const timeSelect = document.getElementById("pickup_time");
  const fulfillmentInputs = document.querySelectorAll('input[name="fulfillment_type"]');
  const paymentInputs = document.querySelectorAll('input[name="payment_method"]');
  const cardFields = document.getElementById("card-fields");
  const cardInputs = cardFields ? cardFields.querySelectorAll("input") : [];
  const cardNumber = document.getElementById("card_number");
  const cardExpiry = document.getElementById("card_expiry");
  const cardCvv = document.getElementById("card_cvv");
  const phoneInput = document.getElementById("customer_phone");
  const scheduledFields = document.getElementById("scheduled-fields");
  const scheduledPanel = document.getElementById("scheduled-pickup-panel");
  const instantPanel = document.getElementById("instant-queue-panel");
  const instantQueueCopy = document.getElementById("instant-queue-copy");
  const instructionsField = document.getElementById("special_instructions");
  const instantNotesField = document.getElementById("special_instructions_instant");
  const pickupPreviewTitle = document.getElementById("pickup-preview-title");
  const pickupPreviewCopy = document.getElementById("pickup-preview-copy");
  const paymentPreviewTitle = document.getElementById("payment-preview-title");
  const paymentPreviewCopy = document.getElementById("payment-preview-copy");
  const submitButton = document.getElementById("checkout-submit");
  const submitIdle = document.getElementById("checkout-submit-idle");
  const inlineStatus = document.getElementById("checkout-inline-status");
  const fields = form ? Array.from(form.querySelectorAll("input, select, textarea")) : [];

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

  function formatPhone(value) {
    const digits = value.replace(/\D/g, "").slice(0, 10);
    if (digits.length <= 4) return digits;
    if (digits.length <= 7) return `${digits.slice(0, 4)} ${digits.slice(4)}`;
    return `${digits.slice(0, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
  }

  function setInlineStatus(message, isError) {
    if (!inlineStatus) return;
    inlineStatus.textContent = message || "";
    inlineStatus.classList.toggle("is-error", Boolean(isError));
  }

  function selectedPaymentInput() {
    return Array.from(paymentInputs).find((input) => input.checked) || null;
  }

  function selectedFulfillmentInput() {
    return Array.from(fulfillmentInputs).find((input) => input.checked) || null;
  }

  function instantSelected() {
    return selectedFulfillmentInput()?.value === "instant";
  }

  function selectedWindow() {
    if (!dateSelect) return null;
    return pickupWindows.find((window) => window.date === dateSelect.value) || null;
  }

  function renderTimeOptions() {
    if (!dateSelect || !timeSelect) return;

    const previous = timeSelect.value;
    const window = selectedWindow();
    const slots = window ? window.slots : [];
    timeSelect.innerHTML = "";
    let selectedValue = "";

    slots.forEach((slot) => {
      const option = document.createElement("option");
      option.value = slot.value;
      option.textContent = `${slot.label} · ${slot.availability_reason}`;
      option.dataset.slotAvailable = String(slot.is_available);
      option.dataset.slotReason = slot.availability_reason;
      option.disabled = !slot.is_available;
      if (slot.is_available && (slot.value === previous || (!selectedValue && !previous))) {
        selectedValue = slot.value;
        option.selected = true;
      }
      timeSelect.appendChild(option);
    });

    if (!selectedValue) {
      const firstAvailable = Array.from(timeSelect.options).find((option) => !option.disabled);
      if (firstAvailable) {
        firstAvailable.selected = true;
      }
    }
  }

  function updatePickupPreview() {
    if (!pickupPreviewTitle || !pickupPreviewCopy) return;

    if (instantSelected()) {
      const queueNumber = Number(instantQueue.next_queue_number || 0);
      const queueLabel = queueNumber > 0 ? `#${String(queueNumber).padStart(3, "0")}` : "Pending queue";
      pickupPreviewTitle.textContent = `Instant queue ${queueLabel}`;
      pickupPreviewCopy.textContent = instantQueue.status_message || "Queue position and ETA are assigned after payment confirmation.";
      if (instantQueueCopy) {
        if (instantQueue.can_accept) {
          instantQueueCopy.textContent = `Queue ${queueLabel} at ${instantQueue.counter_label} with an estimated ${instantQueue.quoted_wait_minutes} minute wait (ready around ${instantQueue.estimated_ready_label}).`;
        } else {
          instantQueueCopy.textContent = instantQueue.status_message || "Instant queue is currently unavailable.";
        }
      }
      return;
    }

    if (!dateSelect || !timeSelect) return;
    const window = selectedWindow();
    const selectedOption = timeSelect.options[timeSelect.selectedIndex];
    pickupPreviewTitle.textContent = window ? window.label : "Choose a pickup day";
    pickupPreviewCopy.textContent = `Selected pickup time: ${selectedOption ? selectedOption.textContent : "Choose a time"}`;
  }

  function updateSubmitLabel() {
    if (!submitIdle || !submitButton) return;
    const total = submitButton.dataset.grandTotal || "";
    if (instantSelected()) {
      submitIdle.textContent = `Pay ${total} & Join Instant Queue`;
    } else {
      submitIdle.textContent = `Pay ${total} & Confirm Scheduled Pickup`;
    }
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

  function syncSpecialInstructions() {
    if (!instructionsField || !instantNotesField) return;
    instructionsField.value = instantNotesField.value;
  }

  function syncFulfillmentUI() {
    const useInstant = instantSelected();
    if (scheduledFields) {
      scheduledFields.hidden = useInstant;
    }
    if (scheduledPanel) {
      scheduledPanel.hidden = useInstant;
    }
    if (instantPanel) {
      instantPanel.hidden = !useInstant;
    }
    if (dateSelect) {
      dateSelect.disabled = useInstant;
    }
    if (timeSelect) {
      timeSelect.disabled = useInstant;
    }
    if (instructionsField && instantNotesField && useInstant) {
      instantNotesField.value = instructionsField.value;
    }
    updatePickupPreview();
    updateSubmitLabel();
  }

  function readDraft() {
    try {
      return JSON.parse(window.sessionStorage.getItem(draftKey) || "{}");
    } catch {
      return {};
    }
  }

  function writeDraft() {
    if (!form) return;
    const payload = {};
    fields.forEach((field) => {
      if (!field.name) return;
      if ((field.type === "radio" || field.type === "checkbox") && !field.checked) return;
      payload[field.name] = field.value;
    });
    window.sessionStorage.setItem(draftKey, JSON.stringify(payload));
  }

  function restoreDraft() {
    if (!form) return;
    const payload = readDraft();
    fields.forEach((field) => {
      if (!field.name) return;
      const value = payload[field.name];
      if (typeof value !== "string") return;
      if (field.type === "radio") {
        field.checked = field.value === value;
        return;
      }
      if (field.tagName === "SELECT" || !field.value) {
        field.value = value;
      }
    });

    if (!selectedFulfillmentInput() && fulfillmentInputs.length) {
      const firstEnabled = Array.from(fulfillmentInputs).find((input) => !input.disabled);
      if (firstEnabled) {
        firstEnabled.checked = true;
      }
    }
  }

  async function handleCartAction(itemId, action, quantity) {
    if (!window.McqCart) return;
    setInlineStatus("Updating checkout basket...", false);
    try {
      if (action === "remove") {
        await window.McqCart.remove(itemId);
      } else {
        await window.McqCart.setQuantity(itemId, quantity);
      }
      writeDraft();
      window.location.reload();
    } catch (error) {
      setInlineStatus(error.message || "Could not update checkout basket.", true);
    }
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
      writeDraft();
    });
  });

  fulfillmentInputs.forEach((input) => {
    input.addEventListener("change", () => {
      syncFulfillmentUI();
      writeDraft();
    });
  });

  if (dateSelect) {
    dateSelect.addEventListener("change", () => {
      renderTimeOptions();
      updatePickupPreview();
      writeDraft();
    });
  }

  if (timeSelect) {
    timeSelect.addEventListener("change", () => {
      updatePickupPreview();
      writeDraft();
    });
  }

  if (instantNotesField && instructionsField) {
    instantNotesField.addEventListener("input", () => {
      syncSpecialInstructions();
      writeDraft();
    });
    instructionsField.addEventListener("input", () => {
      if (!instantSelected()) return;
      instantNotesField.value = instructionsField.value;
      writeDraft();
    });
  }

  if (cardNumber) {
    cardNumber.addEventListener("input", () => {
      cardNumber.value = formatCardNumber(cardNumber.value);
      writeDraft();
    });
  }

  if (cardExpiry) {
    cardExpiry.addEventListener("input", () => {
      cardExpiry.value = formatExpiry(cardExpiry.value);
      writeDraft();
    });
  }

  if (cardCvv) {
    cardCvv.addEventListener("input", () => {
      cardCvv.value = formatCvv(cardCvv.value);
      writeDraft();
    });
  }

  if (phoneInput) {
    phoneInput.addEventListener("input", () => {
      phoneInput.value = formatPhone(phoneInput.value);
      writeDraft();
    });
  }

  if (form) {
    fields.forEach((field) => {
      if (field === cardNumber || field === cardExpiry || field === cardCvv || field === phoneInput) return;
      field.addEventListener("input", writeDraft);
      field.addEventListener("change", writeDraft);
    });

    form.addEventListener("submit", (event) => {
      if (!submitButton) return;
      if (submitButton.disabled) {
        event.preventDefault();
        return;
      }
      syncSpecialInstructions();
      writeDraft();
      submitButton.disabled = true;
      submitButton.classList.add("is-busy");
      setInlineStatus("Submitting checkout and processing payment...", false);
    });
  }

  document.querySelectorAll("[data-checkout-item]").forEach((line) => {
    const itemId = line.dataset.checkoutItem;
    const quantity = Number(line.dataset.quantity || "0");
    line.querySelectorAll("[data-cart-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.cartAction;
        if (action === "increase") {
          handleCartAction(itemId, action, quantity + 1);
        } else if (action === "decrease") {
          if (quantity <= 1) {
            handleCartAction(itemId, "remove", 0);
            return;
          }
          handleCartAction(itemId, action, quantity - 1);
        } else {
          handleCartAction(itemId, action, 0);
        }
      });
    });
  });

  restoreDraft();
  renderTimeOptions();
  updateCardFields();
  syncFulfillmentUI();
  updatePickupPreview();
  updatePaymentPreview();
  updateSubmitLabel();
  writeDraft();
  window.setTimeout(scrollToActiveSection, 120);
})();
