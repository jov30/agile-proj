(() => {
  function el(tag, props = {}, children = []) {
    const node = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (k === "className") node.className = v;
      else if (k === "text") node.textContent = v;
      else node.setAttribute(k, v);
    });
    children.forEach((child) => node.appendChild(child));
    return node;
  }

  async function api(url, options = {}) {
    const resp = await fetch(url, {
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      ...options,
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || "Request failed");
    return data;
  }

  function panelRoot() {
    return document.getElementById("db-feature-panel");
  }

  function setMessage(root, msg, isError = false) {
    const box = root.querySelector('[data-role="msg"]');
    if (!box) return;
    box.textContent = msg || "";
    box.style.color = isError ? "#b42318" : "#127a57";
  }

  function commonPanel(title) {
    const root = panelRoot();
    if (!root) return null;
    root.innerHTML = "";
    root.appendChild(el("h3", { text: title }));
    root.appendChild(el("p", { "data-role": "msg", text: "" }));
    return root;
  }

  async function loadLogin() {
    const root = commonPanel("Sign in");
    if (!root) return;
    const email = el("input", { type: "email", placeholder: "Email", required: "true" });
    const password = el("input", { type: "password", placeholder: "Password", required: "true" });
    const btn = el("button", { type: "submit", className: "button button--primary", text: "Login" });
    const form = el("form");
    [email, password, btn].forEach((n) => form.appendChild(n));
    form.style.display = "grid";
    form.style.gap = "0.7rem";
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      setMessage(root, "");
      try {
        const data = await api("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({ email: email.value.trim(), password: password.value }),
        });
        setMessage(root, `Logged in as ${data.username}`);
      } catch (err) {
        setMessage(root, err.message, true);
      }
    });
    root.appendChild(form);
  }

  async function loadRegister() {
    const root = commonPanel("Create account");
    if (!root) return;
    const username = el("input", { type: "text", placeholder: "Username", required: "true" });
    const email = el("input", { type: "email", placeholder: "Email", required: "true" });
    const password = el("input", { type: "password", placeholder: "Password (min 8 chars)", required: "true" });
    const btn = el("button", { type: "submit", className: "button button--primary", text: "Register" });
    const form = el("form");
    [username, email, password, btn].forEach((n) => form.appendChild(n));
    form.style.display = "grid";
    form.style.gap = "0.7rem";
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      setMessage(root, "");
      try {
        const data = await api("/api/auth/register", {
          method: "POST",
          body: JSON.stringify({
            username: username.value.trim(),
            email: email.value.trim(),
            password: password.value,
          }),
        });
        setMessage(root, `Registered and logged in as ${data.username}`);
      } catch (err) {
        setMessage(root, err.message, true);
      }
    });
    root.appendChild(form);
  }

  async function loadProfile() {
    const root = commonPanel("Profile");
    if (!root) return;
    try {
      const me = await api("/api/user/profile");
      const username = el("input", { type: "text", value: me.username, required: "true" });
      const email = el("input", { type: "email", value: me.email, required: "true" });
      const save = el("button", { type: "submit", className: "button button--primary", text: "Save profile" });
      const logout = el("button", { type: "button", className: "button button--secondary", text: "Logout" });
      const form = el("form");
      [username, email, save, logout].forEach((n) => form.appendChild(n));
      form.style.display = "grid";
      form.style.gap = "0.7rem";
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          await api("/api/user/profile", {
            method: "PATCH",
            body: JSON.stringify({ username: username.value.trim(), email: email.value.trim() }),
          });
          setMessage(root, "Profile updated.");
        } catch (err) {
          setMessage(root, err.message, true);
        }
      });
      logout.addEventListener("click", async () => {
        await api("/api/auth/logout", { method: "POST" });
        setMessage(root, "Logged out.");
      });
      root.appendChild(form);
    } catch (err) {
      setMessage(root, "Please login first.", true);
    }
  }

  async function loadFavorites() {
    const root = commonPanel("Favorites");
    if (!root) return;
    const input = el("input", { type: "text", placeholder: "Menu item id (e.g. pho-noodle-soup__raw-beef-pho)" });
    const add = el("button", { type: "button", className: "button button--primary", text: "Add favorite" });
    const list = el("ul");
    list.style.lineHeight = "1.8";
    root.appendChild(input);
    root.appendChild(add);
    root.appendChild(list);

    async function refresh() {
      const data = await api("/api/user/favorites");
      list.innerHTML = "";
      data.favorites.forEach((row) => {
        const rm = el("button", { type: "button", text: "remove" });
        rm.style.marginLeft = "0.6rem";
        rm.addEventListener("click", async () => {
          await api(`/api/user/favorites/${encodeURIComponent(row.item_id)}`, { method: "DELETE" });
          await refresh();
        });
        const li = el("li", { text: row.item_id });
        li.appendChild(rm);
        list.appendChild(li);
      });
    }

    add.addEventListener("click", async () => {
      try {
        await api("/api/user/favorites", {
          method: "POST",
          body: JSON.stringify({ item_id: input.value.trim() }),
        });
        input.value = "";
        await refresh();
      } catch (err) {
        setMessage(root, err.message, true);
      }
    });

    try {
      await refresh();
    } catch (err) {
      setMessage(root, "Please login first.", true);
    }
  }

  async function loadSharedMeals() {
    const root = commonPanel("Shared meals");
    if (!root) return;
    const item = el("input", { type: "text", placeholder: "Menu item id" });
    const caption = el("input", { type: "text", placeholder: "Short caption" });
    const post = el("button", { type: "button", className: "button button--primary", text: "Share meal" });
    const list = el("ul");
    list.style.lineHeight = "1.8";
    root.appendChild(item);
    root.appendChild(caption);
    root.appendChild(post);
    root.appendChild(list);

    async function refresh() {
      const data = await api("/api/user/shared-meals");
      list.innerHTML = "";
      data.shared_meals.forEach((row) => {
        list.appendChild(el("li", { text: `${row.item_id} — ${row.author}${row.caption ? `: ${row.caption}` : ""}` }));
      });
    }

    post.addEventListener("click", async () => {
      try {
        await api("/api/user/shared-meals", {
          method: "POST",
          body: JSON.stringify({ item_id: item.value.trim(), caption: caption.value.trim() }),
        });
        item.value = "";
        caption.value = "";
        await refresh();
      } catch (err) {
        setMessage(root, err.message, true);
      }
    });

    await refresh();
  }

  async function loadCheckout() {
    const root = commonPanel("Checkout");
    if (!root) return;
    const pickup = el("input", { type: "datetime-local" });
    const submit = el("button", { type: "button", className: "button button--primary", text: "Place order" });
    root.appendChild(pickup);
    root.appendChild(submit);
    submit.addEventListener("click", async () => {
      try {
        const payload = {};
        if (pickup.value) payload.pickup_at = new Date(pickup.value).toISOString();
        const data = await api("/api/orders/checkout", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setMessage(root, `Order #${data.order_id} created.`);
      } catch (err) {
        setMessage(root, err.message, true);
      }
    });
  }

  async function loadOrders() {
    const root = commonPanel("My orders");
    if (!root) return;
    const list = el("ul");
    list.style.lineHeight = "1.8";
    root.appendChild(list);
    try {
      const data = await api("/api/orders/my");
      data.orders.forEach((o) => {
        list.appendChild(el("li", { text: `#${o.id} • ${o.status} • $${(o.total_cents / 100).toFixed(2)} • ${o.items.length} items` }));
      });
    } catch (err) {
      setMessage(root, err.message, true);
    }
  }

  const path = window.location.pathname;
  if (path === "/login") loadLogin();
  else if (path === "/register") loadRegister();
  else if (path === "/profile") loadProfile();
  else if (path === "/favorites") loadFavorites();
  else if (path === "/shared-meals") loadSharedMeals();
  else if (path === "/checkout") loadCheckout();
  else if (path === "/orders") loadOrders();
})();
