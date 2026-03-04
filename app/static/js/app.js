(function () {
  "use strict";

  const REFRESH_INTERVAL_MS = 30_000;
  let selectedPortfolioId = null;
  let lookupResult = null;
  let lookupTimer = null;

  // ── DOM refs ──────────────────────────────────────────────
  const $portfolioList = document.getElementById("portfolio-list");
  const $createForm = document.getElementById("create-portfolio-form");
  const $nameInput = document.getElementById("portfolio-name-input");
  const $emptyState = document.getElementById("empty-state");
  const $detail = document.getElementById("portfolio-detail");
  const $title = document.getElementById("portfolio-title");
  const $summary = document.getElementById("portfolio-summary");
  const $stocksTbody = document.getElementById("stocks-tbody");
  const $noStocksMsg = document.getElementById("no-stocks-msg");
  const $addStockBtn = document.getElementById("add-stock-btn");
  const $modal = document.getElementById("add-stock-modal");
  const $modalBackdrop = document.getElementById("modal-backdrop");
  const $modalCancel = document.getElementById("modal-cancel");
  const $addStockForm = document.getElementById("add-stock-form");
  const $modalSubmit = document.getElementById("modal-submit");
  const $marketSelect = document.getElementById("stock-market");
  const $tickerInput = document.getElementById("stock-ticker");
  const $lookupStatus = document.getElementById("lookup-status");
  const $lookupPreview = document.getElementById("lookup-preview");
  const $previewName = document.getElementById("preview-name");
  const $previewPrice = document.getElementById("preview-price");
  const $stockQty = document.getElementById("stock-qty");
  const $stockBuyPrice = document.getElementById("stock-buy-price");
  const $lastUpdated = document.getElementById("last-updated");
  const $editModal = document.getElementById("edit-stock-modal");
  const $editModalBackdrop = document.getElementById("edit-modal-backdrop");
  const $editModalCancel = document.getElementById("edit-modal-cancel");
  const $editForm = document.getElementById("edit-stock-form");
  const $editStockId = document.getElementById("edit-stock-id");
  const $editStockLabel = document.getElementById("edit-stock-label");
  const $editQty = document.getElementById("edit-qty");
  const $editBuyPrice = document.getElementById("edit-buy-price");

  // ── API helpers ───────────────────────────────────────────
  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
    if (res.status === 204) return null;
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    return res.json();
  }

  // ── Portfolios ────────────────────────────────────────────
  async function loadPortfolios() {
    const portfolios = await api("/api/portfolios");
    renderPortfolioList(portfolios);
    if (selectedPortfolioId) {
      const still = portfolios.find((p) => p.id === selectedPortfolioId);
      if (!still) deselectPortfolio();
    }
  }

  function renderPortfolioList(portfolios) {
    $portfolioList.innerHTML = "";
    if (portfolios.length === 0) {
      $portfolioList.innerHTML =
        '<p class="text-xs text-gray-400 text-center py-6">No portfolios yet</p>';
      return;
    }
    for (const p of portfolios) {
      const el = document.createElement("div");
      const isActive = p.id === selectedPortfolioId;
      el.className = `flex items-center justify-between rounded-lg px-3 py-2.5 cursor-pointer transition-colors ${
        isActive
          ? "bg-indigo-50 text-indigo-700"
          : "text-gray-700 hover:bg-gray-100"
      }`;
      const plSign = p.total_value - p.total_cost;
      const plClass = plSign >= 0 ? "profit" : "loss";
      const plPrefix = plSign >= 0 ? "+" : "";
      el.innerHTML = `
        <div class="min-w-0 flex-1" data-select="${p.id}">
          <p class="text-sm font-medium truncate">${esc(p.name)}</p>
          <p class="text-xs text-gray-400 mt-0.5">
            Value: ${fmt(p.total_value)}
            <span class="${plClass}">(${plPrefix}${fmt(plSign)})</span>
          </p>
        </div>
        <button data-delete="${p.id}" title="Delete portfolio"
          class="ml-2 p-1 rounded hover:bg-red-100 text-gray-400 hover:text-red-600 transition-colors flex-shrink-0">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>`;
      $portfolioList.appendChild(el);
    }
  }

  $portfolioList.addEventListener("click", async (e) => {
    const selectEl = e.target.closest("[data-select]");
    const deleteEl = e.target.closest("[data-delete]");
    if (deleteEl) {
      e.stopPropagation();
      const id = Number(deleteEl.dataset.delete);
      if (!confirm("Delete this portfolio and all its stocks?")) return;
      await api(`/api/portfolios/${id}`, { method: "DELETE" });
      if (selectedPortfolioId === id) deselectPortfolio();
      loadPortfolios();
      return;
    }
    if (selectEl) {
      selectPortfolio(Number(selectEl.dataset.select));
    }
  });

  $createForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = $nameInput.value.trim();
    if (!name) return;
    await api("/api/portfolios", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    $nameInput.value = "";
    loadPortfolios();
  });

  function selectPortfolio(id) {
    selectedPortfolioId = id;
    $emptyState.classList.add("hidden");
    $detail.classList.remove("hidden");
    loadPortfolios();
    loadStocks();
  }

  function deselectPortfolio() {
    selectedPortfolioId = null;
    $emptyState.classList.remove("hidden");
    $detail.classList.add("hidden");
  }

  // ── Stocks ────────────────────────────────────────────────
  async function loadStocks() {
    if (!selectedPortfolioId) return;
    const stocks = await api(
      `/api/portfolios/${selectedPortfolioId}/stocks`
    );
    renderStocks(stocks);
  }

  function renderStocks(stocks) {
    if (stocks.length === 0) {
      $stocksTbody.innerHTML = "";
      $noStocksMsg.classList.remove("hidden");
      $title.textContent =
        document.querySelector(`[data-select="${selectedPortfolioId}"]`)
          ?.querySelector(".font-medium")?.textContent || "Portfolio";
      $summary.textContent = "No holdings";
      return;
    }
    $noStocksMsg.classList.add("hidden");

    let totalValue = 0;
    let totalCost = 0;
    $stocksTbody.innerHTML = "";

    for (const s of stocks) {
      totalValue += s.market_value;
      totalCost += s.buy_price * s.quantity;
      const pl = s.profit_loss;
      const plClass = pl >= 0 ? "profit" : "loss";
      const plPrefix = pl >= 0 ? "+" : "";
      const changePct =
        s.price_change_pct != null ? `${s.price_change_pct.toFixed(2)}%` : "—";
      const changeClass =
        s.price_change_pct != null
          ? s.price_change_pct >= 0
            ? "profit"
            : "loss"
          : "";

      const tr = document.createElement("tr");
      tr.className = "hover:bg-gray-50 transition-colors";
      tr.innerHTML = `
        <td class="px-4 py-3 text-sm font-medium text-gray-900">${esc(s.ticker)}</td>
        <td class="px-4 py-3 text-sm text-gray-600">${esc(s.company_name)}</td>
        <td class="px-4 py-3 text-sm text-gray-500 uppercase">${esc(s.market)}</td>
        <td class="px-4 py-3 text-sm text-right text-gray-900">${fmt(s.current_price)}</td>
        <td class="px-4 py-3 text-sm text-right ${changeClass}">${changePct}</td>
        <td class="px-4 py-3 text-sm text-right text-gray-900">${s.quantity}</td>
        <td class="px-4 py-3 text-sm text-right text-gray-600">${fmt(s.buy_price)}</td>
        <td class="px-4 py-3 text-sm text-right text-gray-900 font-medium">${fmt(s.market_value)}</td>
        <td class="px-4 py-3 text-sm text-right font-medium ${plClass}">${plPrefix}${fmt(pl)}</td>
        <td class="px-4 py-3 text-sm text-right text-gray-700">${s.weight_pct != null ? s.weight_pct.toFixed(2) + "%" : "—"}</td>
        <td class="px-4 py-3 text-right space-x-1">
          <button data-edit='${JSON.stringify({id:s.id,ticker:s.ticker,company_name:s.company_name,quantity:s.quantity,buy_price:s.buy_price})}' class="text-gray-400 hover:text-indigo-600 transition-colors" title="Edit">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/></svg>
          </button>
          <button data-remove="${s.id}" class="text-gray-400 hover:text-red-600 transition-colors" title="Remove">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
          </button>
        </td>`;
      $stocksTbody.appendChild(tr);
    }

    const portfolioName =
      document.querySelector(`[data-select="${selectedPortfolioId}"]`)
        ?.querySelector(".font-medium")?.textContent || "Portfolio";
    $title.textContent = portfolioName;
    const totalPL = totalValue - totalCost;
    const plClass = totalPL >= 0 ? "profit" : "loss";
    const plPrefix = totalPL >= 0 ? "+" : "";
    $summary.innerHTML = `Total value: <strong>${fmt(totalValue)}</strong> &nbsp;|&nbsp; P/L: <strong class="${plClass}">${plPrefix}${fmt(totalPL)}</strong>`;
  }

  $stocksTbody.addEventListener("click", async (e) => {
    const editBtn = e.target.closest("[data-edit]");
    if (editBtn) {
      const stock = JSON.parse(editBtn.dataset.edit);
      openEditModal(stock);
      return;
    }
    const btn = e.target.closest("[data-remove]");
    if (!btn) return;
    const id = Number(btn.dataset.remove);
    await api(`/api/stocks/${id}`, { method: "DELETE" });
    loadStocks();
    loadPortfolios();
  });

  // ── Modal ─────────────────────────────────────────────────
  function openModal() {
    lookupResult = null;
    $addStockForm.reset();
    $lookupPreview.classList.add("hidden");
    $lookupStatus.textContent = "";
    $modalSubmit.disabled = true;
    $modal.classList.remove("hidden");
  }

  function closeModal() {
    $modal.classList.add("hidden");
  }

  $addStockBtn.addEventListener("click", openModal);
  $modalCancel.addEventListener("click", closeModal);
  $modalBackdrop.addEventListener("click", closeModal);

  // ── Ticker Lookup (debounced) ─────────────────────────────
  function debounceLookup() {
    clearTimeout(lookupTimer);
    lookupResult = null;
    $modalSubmit.disabled = true;
    const ticker = $tickerInput.value.trim();
    const market = $marketSelect.value;
    if (!ticker) {
      $lookupPreview.classList.add("hidden");
      $lookupStatus.textContent = "";
      return;
    }
    $lookupStatus.textContent = "Looking up…";
    lookupTimer = setTimeout(() => doLookup(ticker, market), 500);
  }

  async function doLookup(ticker, market) {
    try {
      const data = await api(
        `/api/stocks/lookup?ticker=${encodeURIComponent(ticker)}&market=${market}`
      );
      lookupResult = data;
      $previewName.textContent = data.company_name;
      $previewPrice.textContent = fmt(data.current_price);
      $lookupPreview.classList.remove("hidden");
      $lookupStatus.textContent = "";
      $modalSubmit.disabled = false;
      if (!$stockBuyPrice.value) {
        $stockBuyPrice.value = data.current_price;
      }
    } catch (err) {
      $lookupPreview.classList.add("hidden");
      $lookupStatus.textContent = err.message;
      $lookupStatus.classList.add("text-red-500");
      setTimeout(() => $lookupStatus.classList.remove("text-red-500"), 2000);
    }
  }

  $tickerInput.addEventListener("input", debounceLookup);
  $marketSelect.addEventListener("change", debounceLookup);

  // ── Submit add stock ──────────────────────────────────────
  $addStockForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!lookupResult || !selectedPortfolioId) return;
    const body = {
      ticker: lookupResult.ticker,
      market: lookupResult.market,
      company_name: lookupResult.company_name,
      quantity: parseFloat($stockQty.value),
      buy_price: parseFloat($stockBuyPrice.value),
      current_price: lookupResult.current_price,
    };
    await api(`/api/portfolios/${selectedPortfolioId}/stocks`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    closeModal();
    loadStocks();
    loadPortfolios();
  });

  // ── Edit Stock Modal ───────────────────────────────────────
  function openEditModal(stock) {
    $editStockId.value = stock.id;
    $editStockLabel.textContent = `${stock.ticker} — ${stock.company_name}`;
    $editQty.value = stock.quantity;
    $editBuyPrice.value = stock.buy_price;
    $editModal.classList.remove("hidden");
  }

  function closeEditModal() {
    $editModal.classList.add("hidden");
  }

  $editModalCancel.addEventListener("click", closeEditModal);
  $editModalBackdrop.addEventListener("click", closeEditModal);

  $editForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = $editStockId.value;
    const body = {
      quantity: parseFloat($editQty.value),
      buy_price: parseFloat($editBuyPrice.value),
    };
    await api(`/api/stocks/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    closeEditModal();
    loadStocks();
    loadPortfolios();
  });

  // ── Auto-refresh ──────────────────────────────────────────
  async function refreshPrices() {
    try {
      await api("/api/stocks/refresh", { method: "POST" });
      $lastUpdated.textContent = `Updated: ${new Date().toLocaleTimeString()}`;
      if (selectedPortfolioId) {
        loadStocks();
        loadPortfolios();
      }
    } catch {
      /* ignore refresh errors silently */
    }
  }

  setInterval(refreshPrices, REFRESH_INTERVAL_MS);

  // ── Helpers ───────────────────────────────────────────────
  function fmt(n) {
    if (n == null) return "—";
    return Number(n).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // ── Init ──────────────────────────────────────────────────
  loadPortfolios();
})();
