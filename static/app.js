(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const monthInput = $("filter-month");
  const categorySelect = $("filter-category");

  // Default to the current month.
  monthInput.value = new Date().toISOString().slice(0, 7);

  // ---------- helpers ----------

  function el(tag, props, children) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([key, value]) => {
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    });
    (children || []).forEach((child) => node.appendChild(child));
    return node;
  }

  let toastTimer;
  function toast(message, isError) {
    const box = $("toast");
    box.textContent = message;
    box.className = "toast" + (isError ? " error" : "");
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { box.hidden = true; }, 3500);
  }

  async function api(path, options) {
    const res = await fetch(path, options);
    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON response */ }
    if (!res.ok) throw new Error(data.error || "Request failed (" + res.status + ")");
    return data;
  }

  const jsonOptions = (method, body) => ({
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  function query(params) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) q.set(k, v); });
    const s = q.toString();
    return s ? "?" + s : "";
  }

  // ---------- rendering ----------

  function renderExpenses(expenses) {
    const body = $("expense-rows");
    body.replaceChildren();
    $("expense-empty").hidden = expenses.length > 0;
    expenses.forEach((e) => {
      body.appendChild(el("tr", {}, [
        el("td", { text: e.date }),
        el("td", {}, [el("span", { class: "pill", text: e.category })]),
        el("td", { class: "note", text: e.note }),
        el("td", { class: "num", text: e.amount }),
        el("td", { class: "num" }, [
          el("button", {
            class: "btn small danger", type: "button", "aria-label": "Delete expense " + e.id,
            text: "Delete", onclick: () => removeExpense(e.id),
          }),
        ]),
      ]));
    });
  }

  function renderSummary(summary, expenseCount) {
    $("stat-total").textContent = summary.total;
    $("stat-count").textContent = String(expenseCount);
    $("stat-top").textContent = summary.categories.length ? summary.categories[0].category : "–";

    const list = $("summary-list");
    list.replaceChildren();
    if (!summary.categories.length) {
      list.appendChild(el("p", { class: "empty", text: "Nothing to show yet." }));
      return;
    }
    summary.categories.forEach((c) => {
      list.appendChild(el("div", { class: "bar-row" }, [
        el("div", { class: "bar-head" }, [
          el("span", { text: c.category + " (" + c.count + ")" }),
          el("span", { text: c.total + "  ·  " + Math.round(c.share * 100) + "%" }),
        ]),
        el("div", { class: "track" }, [
          el("div", { class: "fill", style: "width:" + Math.max(2, c.share * 100) + "%" }),
        ]),
      ]));
    });
  }

  function renderMonths(months) {
    const list = $("months-list");
    list.replaceChildren();
    if (!months.length) {
      list.appendChild(el("p", { class: "empty", text: "Nothing to show yet." }));
      return;
    }
    const peak = Math.max(...months.map((m) => m.total_cents));
    months.slice(-12).forEach((m) => {
      list.appendChild(el("div", { class: "bar-row" }, [
        el("div", { class: "bar-head" }, [
          el("span", { text: m.month }),
          el("span", { text: m.total }),
        ]),
        el("div", { class: "track" }, [
          el("div", { class: "fill", style: "width:" + Math.max(2, (m.total_cents / peak) * 100) + "%" }),
        ]),
      ]));
    });
  }

  function renderBudgets(budgets) {
    $("budget-month").textContent = monthInput.value || "this month";
    const list = $("budget-list");
    list.replaceChildren();
    if (!budgets.length) {
      list.appendChild(el("p", { class: "empty", text: "No budgets yet. Set one below." }));
      return;
    }
    budgets.forEach((b) => {
      const pct = Math.min(100, (b.spent_cents / b.limit_cents) * 100);
      const label = b.status === "over" ? "Over budget" : b.status === "close" ? "Almost there" : "On track";
      list.appendChild(el("div", {}, [
        el("div", { class: "budget-top" }, [
          el("strong", { text: b.category }),
          el("button", {
            class: "btn small danger", type: "button", "aria-label": "Remove budget " + b.category,
            text: "Remove", onclick: () => removeBudget(b.category),
          }),
        ]),
        el("div", { class: "track" }, [
          el("div", { class: "fill " + b.status, style: "width:" + Math.max(2, pct) + "%" }),
        ]),
        el("div", { class: "budget-meta" }, [
          el("span", { text: b.spent + " of " + b.limit + "  ·  " }),
          el("span", { class: "status-" + b.status, text: label }),
        ]),
      ]));
    });
  }

  function renderCategoryOptions(categories) {
    const selected = categorySelect.value;
    categorySelect.replaceChildren(el("option", { value: "", text: "All categories" }));
    const datalist = $("category-list");
    datalist.replaceChildren();
    categories.forEach((name) => {
      categorySelect.appendChild(el("option", { value: name, text: name }));
      datalist.appendChild(el("option", { value: name }));
    });
    if (categories.includes(selected)) categorySelect.value = selected;
  }

  // ---------- data loading ----------

  async function refresh() {
    const month = monthInput.value;
    const category = categorySelect.value;
    try {
      const [expenses, summary, allSummary, budgets, months] = await Promise.all([
        api("/api/expenses" + query({ month, category })),
        api("/api/summary" + query({ month })),
        api("/api/summary"),
        api("/api/budgets" + query({ month })),
        api("/api/months"),
      ]);
      renderCategoryOptions(allSummary.categories.map((c) => c.category).sort());
      renderExpenses(expenses.expenses);
      renderSummary(summary, expenses.expenses.length);
      renderBudgets(budgets.budgets);
      renderMonths(months.months);
    } catch (err) {
      toast(err.message, true);
    }
  }

  // ---------- actions ----------

  async function removeExpense(id) {
    if (!confirm("Delete this expense?")) return;
    try {
      await api("/api/expenses/" + id, { method: "DELETE" });
      toast("Expense deleted");
      refresh();
    } catch (err) { toast(err.message, true); }
  }

  async function removeBudget(category) {
    try {
      await api("/api/budgets/" + encodeURIComponent(category), { method: "DELETE" });
      toast("Budget removed");
      refresh();
    } catch (err) { toast(err.message, true); }
  }

  $("add-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      await api("/api/expenses", jsonOptions("POST", data));
      toast("Expense added");
      form.amount.value = "";
      form.note.value = "";
      form.amount.focus();
      refresh();
    } catch (err) { toast(err.message, true); }
  });

  $("budget-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const data = Object.fromEntries(new FormData(form).entries());
    try {
      await api("/api/budgets", jsonOptions("PUT", data));
      toast("Budget saved");
      form.reset();
      refresh();
    } catch (err) { toast(err.message, true); }
  });

  $("import-file").addEventListener("change", async (event) => {
    const input = event.target;
    if (!input.files.length) return;
    const body = new FormData();
    body.append("file", input.files[0]);
    try {
      const result = await api("/api/import", { method: "POST", body });
      toast("Imported " + result.imported + " expense(s)");
      refresh();
    } catch (err) { toast(err.message, true); }
    input.value = "";
  });

  $("clear-month").addEventListener("click", () => { monthInput.value = ""; refresh(); });
  monthInput.addEventListener("change", refresh);
  categorySelect.addEventListener("change", refresh);

  refresh();
})();
