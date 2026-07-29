let portfolioChart = null;
let cardHistoryChart = null;
let refreshActive = false;

window.addEventListener("DOMContentLoaded", () => {
  setupChart();
  setupCollectionTools();
  setupCardInteractions();
  setupWishlist();
  setupRefresh();
  setupDialogClosers();
  const linkedCard = new URLSearchParams(window.location.search).get("card");
  if (linkedCard) openCard(linkedCard);
});

function setupChart() {
  const canvas = document.getElementById("valueChart");
  const dataNode = document.getElementById("historyData");
  if (!canvas || !dataNode || !window.Chart) return;
  const allRows = JSON.parse(dataNode.textContent || "[]");
  let activeRows = filterRows(allRows, 180);
  portfolioChart = new Chart(canvas, {
    type: "line",
    data: chartData(activeRows, chartTheme(), "Collection Value"),
    options: chartOptions(chartTheme(), true),
  });
  document.querySelectorAll("[data-days]").forEach(button => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-days]").forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      activeRows = filterRows(allRows, Number(button.dataset.days || 0));
      portfolioChart.data = chartData(activeRows, chartTheme(), "Collection Value");
      portfolioChart.update();
    });
  });
  window.addEventListener("themechange", () => {
    const theme = chartTheme();
    portfolioChart.data = chartData(activeRows, theme, "Collection Value");
    portfolioChart.options = chartOptions(theme, true);
    portfolioChart.update();
    if (cardHistoryChart) {
      cardHistoryChart.data.datasets[0].borderColor = theme.line;
      cardHistoryChart.options = chartOptions(theme, true);
      cardHistoryChart.update();
    }
  });
}

function chartData(rows, theme, label) {
  return {
    labels: rows.map(row => row.date),
    datasets: [{
      label,
      data: rows.map(row => row.value),
      borderColor: theme.line,
      backgroundColor: theme.fill,
      borderWidth: 2,
      fill: true,
      tension: 0.25,
      pointRadius: rows.length < 12 ? 3 : 0,
    }],
  };
}

function chartOptions(theme, currencyTicks) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: "index" },
    plugins: {
      legend: { display: false },
      tooltip: { backgroundColor: theme.tooltipBg, titleColor: theme.text, bodyColor: theme.text, borderColor: theme.grid, borderWidth: 1 },
    },
    scales: {
      x: { grid: { color: theme.grid }, ticks: { color: theme.tick, maxTicksLimit: 6 } },
      y: { beginAtZero: false, grid: { color: theme.grid }, ticks: { color: theme.tick, callback: value => currencyTicks ? `$${Number(value).toFixed(2)}` : value } },
    },
  };
}

function chartTheme() {
  const styles = getComputedStyle(document.documentElement);
  return {
    line: cssVar(styles, "--chart-line", "#2563eb"),
    fill: cssVar(styles, "--chart-fill", "rgba(37, 99, 235, 0.10)"),
    grid: cssVar(styles, "--chart-grid", "rgba(100, 116, 139, 0.22)"),
    tick: cssVar(styles, "--chart-tick", "#667085"),
    text: cssVar(styles, "--text", "#111827"),
    tooltipBg: cssVar(styles, "--surface", "#ffffff"),
  };
}

function cssVar(styles, name, fallback) {
  return styles.getPropertyValue(name).trim() || fallback;
}

function filterRows(rows, days) {
  if (!days || rows.length === 0) return rows;
  const cutoff = new Date(rows[rows.length - 1].date);
  cutoff.setDate(cutoff.getDate() - days);
  return rows.filter(row => new Date(row.date) >= cutoff);
}

function setupCollectionTools() {
  const search = document.getElementById("collectionSearch");
  const game = document.getElementById("gameFilter");
  const sort = document.getElementById("sortCards");
  const list = document.getElementById("cardList");
  if (!list) return;
  const cards = Array.from(list.querySelectorAll(".card-row"));
  const apply = () => {
    const term = (search?.value || "").trim().toLowerCase();
    const gameValue = game?.value || "all";
    const sortValue = sort?.value || "value";
    cards.forEach(card => {
      card.hidden = !((!term || card.dataset.name.includes(term)) && (gameValue === "all" || card.dataset.game === gameValue));
    });
    cards.filter(card => !card.hidden).sort((a, b) => compareCards(a, b, sortValue)).forEach(card => list.appendChild(card));
  };
  [search, game, sort].forEach(control => control?.addEventListener("input", apply));
}

function compareCards(a, b, sortValue) {
  if (sortValue === "name") return a.dataset.name.localeCompare(b.dataset.name);
  if (sortValue === "game") return a.dataset.game.localeCompare(b.dataset.game);
  if (sortValue === "unpriced") return a.dataset.priced.localeCompare(b.dataset.priced);
  if (sortValue === "profit") return Number(b.dataset.profit || 0) - Number(a.dataset.profit || 0);
  return Number(b.dataset.value || 0) - Number(a.dataset.value || 0);
}

function setupCardInteractions() {
  document.querySelectorAll("[data-card-id]").forEach(row => row.addEventListener("click", () => openCard(row.dataset.cardId)));
  document.querySelectorAll("[data-open-card]").forEach(row => row.addEventListener("click", () => openCard(row.dataset.openCard)));
}

async function openCard(cardId) {
  if (!cardId) return;
  const dialog = document.getElementById("cardDialog");
  const content = document.getElementById("cardDialogContent");
  content.innerHTML = '<div class="drawer-loading"><strong>Loading card details...</strong></div>';
  dialog.showModal();
  try {
    const card = await window.tcgApiFetch(`/api/cards/${encodeURIComponent(cardId)}`);
    renderCardDetail(card);
  } catch (error) {
    content.innerHTML = `<div class="empty-state"><h3>Could not open card</h3><p>${window.tcgEscape(error.message)}</p></div>`;
  }
}

function renderCardDetail(card) {
  const content = document.getElementById("cardDialogContent");
  const source = window.tcgEscape(card.source || "Price source unavailable");
  content.innerHTML = `
    <section class="drawer-hero">
      <div class="drawer-card-art">${card.image ? `<img src="${window.tcgEscapeAttr(card.image)}" alt="${window.tcgEscapeAttr(card.name)}">` : `<span>${window.tcgEscape(card.game)}</span>`}</div>
      <div class="drawer-card-heading">
        <div class="watch-title-line"><span class="badge badge-${window.tcgEscape(card.game)}">${window.tcgEscape(card.game)}</span>${card.stale ? '<span class="muted-pill">Last-known price</span>' : ''}</div>
        <h2 id="cardDialogTitle">${window.tcgEscape(card.name)}</h2>
        <p>${window.tcgEscape(card.set || "Set unknown")}</p>
        <strong class="drawer-price">${window.tcgMoney(card.value, card.currency)}</strong>
        <small>${source} · ${window.tcgEscape(card.price_as_of || "not refreshed")}</small>
        ${card.uri && card.uri !== "#" ? `<a class="text-link" href="${window.tcgEscapeAttr(card.uri)}" target="_blank" rel="noopener">Open market page</a>` : ""}
      </div>
    </section>
    <section class="detail-metrics">
      <div><span>Market / card</span><strong>${window.tcgMoney(card.price, card.currency)}</strong></div>
      <div><span>Condition estimate</span><strong>${window.tcgMoney(card.unit_value, card.currency)}</strong><small>${Math.round(Number(card.condition_multiplier || 1) * 100)}% of market</small></div>
      <div><span>Cost basis</span><strong>${card.buy_price == null ? "N/A" : window.tcgMoney(Number(card.buy_price) * Number(card.quantity || 1), card.currency)}</strong></div>
      <div><span>Unrealized P/L</span><strong class="${Number(card.profit_loss || 0) >= 0 ? "positive" : "negative"}">${window.tcgMoney(card.profit_loss, card.currency)}</strong></div>
    </section>
    <section class="card-history-section">
      <div class="section-heading"><h3>Price History</h3><span>${card.history.length} ${card.history.length === 1 ? "point" : "points"}</span></div>
      <div class="mini-chart"><canvas id="cardHistoryCanvas"></canvas></div>
    </section>
    <form class="form-stack detail-edit-form" id="editCardForm">
      <div class="section-heading"><h3>Collection Details</h3><span>Condition values are estimates</span></div>
      <label class="field-label">Card name or ID<input class="input" id="editCardName" value="${window.tcgEscapeAttr(card.editable_name || card.name)}" required></label>
      <div class="form-grid">
        <label class="field-label">Quantity<input class="input" id="editQuantity" type="number" min="1" value="${Number(card.quantity || 1)}" required></label>
        <label class="field-label">Purchase price / card<input class="input" id="editBuyPrice" type="number" min="0" step="0.01" value="${card.buy_price == null ? "" : Number(card.buy_price).toFixed(2)}"></label>
        <label class="field-label">Condition<select class="input" id="editCondition">${conditionOptions(card.condition)}</select></label>
        <label class="field-label">Finish<select class="input" id="editFinish">${finishOptions(card.finish)}</select></label>
      </div>
      <button class="button" type="submit">Save Changes</button>
    </form>
    <details class="sale-panel">
      <summary>Record a Sale</summary>
      <form class="form-stack" id="saleForm">
        <div class="form-grid">
          <label class="field-label">Quantity<input class="input" id="saleQuantity" type="number" min="1" max="${Number(card.quantity || 1)}" value="1" required></label>
          <label class="field-label">Sale price / card<input class="input" id="salePrice" type="number" min="0" step="0.01" required></label>
          <label class="field-label">Fees<input class="input" id="saleFees" type="number" min="0" step="0.01" value="0"></label>
          <label class="field-label">Shipping<input class="input" id="saleShipping" type="number" min="0" step="0.01" value="0"></label>
        </div>
        <label class="field-label">Notes<input class="input" id="saleNotes" maxlength="300"></label>
        <button class="button" type="submit">Complete Sale</button>
      </form>
    </details>
    <div class="danger-zone">
      <button class="text-button" id="archiveCardButton" type="button">Archive without sale</button>
      <button class="text-button danger-text" id="deleteCardButton" type="button">Delete permanently</button>
    </div>`;

  drawCardHistory(card.history);
  document.getElementById("editCardForm").addEventListener("submit", event => updateCard(event, card.card_id));
  document.getElementById("saleForm").addEventListener("submit", event => sellCard(event, card.card_id));
  document.getElementById("archiveCardButton").addEventListener("click", () => archiveCard(card.card_id));
  document.getElementById("deleteCardButton").addEventListener("click", () => deleteCard(card.card_id));
}

function drawCardHistory(rows) {
  const canvas = document.getElementById("cardHistoryCanvas");
  if (!canvas || !window.Chart) return;
  cardHistoryChart?.destroy();
  cardHistoryChart = new Chart(canvas, {
    type: "line",
    data: chartData(rows, chartTheme(), "Unit Value"),
    options: chartOptions(chartTheme(), true),
  });
}

function conditionOptions(selected) {
  return [["M", "Mint"], ["NM", "Near Mint"], ["LP", "Lightly Played"], ["MP", "Moderately Played"], ["HP", "Heavily Played"], ["DMG", "Damaged"]]
    .map(([value, label]) => `<option value="${value}" ${value === selected ? "selected" : ""}>${label} (${value})</option>`).join("");
}

function finishOptions(selected) {
  return ["regular", "foil", "etched"].map(value => `<option value="${value}" ${value === selected ? "selected" : ""}>${value[0].toUpperCase()}${value.slice(1)}</option>`).join("");
}

async function updateCard(event, cardId) {
  event.preventDefault();
  const payload = {
    card_line: document.getElementById("editCardName").value,
    quantity: document.getElementById("editQuantity").value,
    buy_price: document.getElementById("editBuyPrice").value,
    condition: document.getElementById("editCondition").value,
    finish: document.getElementById("editFinish").value,
  };
  await performAndReload(`/api/cards/${cardId}`, { method: "PATCH", body: JSON.stringify(payload) }, "Card updated");
}

async function sellCard(event, cardId) {
  event.preventDefault();
  const payload = {
    quantity: document.getElementById("saleQuantity").value,
    unit_price: document.getElementById("salePrice").value,
    fees: document.getElementById("saleFees").value,
    shipping: document.getElementById("saleShipping").value,
    notes: document.getElementById("saleNotes").value,
  };
  await performAndReload(`/api/cards/${cardId}/sell`, { method: "POST", body: JSON.stringify(payload) }, "Sale recorded");
}

async function archiveCard(cardId) {
  if (!window.confirm("Archive this card and remove it from the active collection?")) return;
  await performAndReload(`/api/cards/${cardId}/archive`, { method: "POST", body: JSON.stringify({}) }, "Card archived");
}

async function deleteCard(cardId) {
  if (!window.confirm("Permanently delete this card? This does not create a sale record.")) return;
  await performAndReload(`/api/cards/${cardId}`, { method: "DELETE" }, "Card deleted");
}

async function performAndReload(url, options, message) {
  try {
    await window.tcgApiFetch(url, options);
    window.tcgToast(message, "success");
    setTimeout(() => window.location.reload(), 450);
  } catch (error) {
    window.tcgToast(error.message, "error");
  }
}

function setupWishlist() {
  document.getElementById("addWishlistButton")?.addEventListener("click", () => openWishlistEditor());
  document.getElementById("emptyWishlistButton")?.addEventListener("click", () => openWishlistEditor());
  document.querySelectorAll(".edit-wishlist").forEach(button => button.addEventListener("click", () => openWishlistEditor(JSON.parse(button.dataset.wishlist))));
  document.getElementById("wishlistForm")?.addEventListener("submit", saveWishlist);
  document.getElementById("deleteWishlistButton")?.addEventListener("click", deleteWishlist);
}

function openWishlistEditor(item = null) {
  document.getElementById("wishlistDialogTitle").textContent = item ? "Edit Wishlist Target" : "Add Wishlist Target";
  document.getElementById("wishlistId").value = item?.wishlist_id || "";
  document.getElementById("wishlistGame").value = item?.game || "MTG";
  document.getElementById("wishlistCardLine").value = item?.card_line || "";
  document.getElementById("wishlistOperator").value = item?.operator || "<";
  document.getElementById("wishlistTarget").value = item?.target_price ?? "";
  document.getElementById("wishlistAlert").checked = item?.alert_enabled ?? true;
  document.getElementById("deleteWishlistButton").hidden = !item;
  document.getElementById("wishlistDialog").showModal();
}

async function saveWishlist(event) {
  event.preventDefault();
  const wishlistId = document.getElementById("wishlistId").value;
  const payload = {
    game: document.getElementById("wishlistGame").value,
    card_line: document.getElementById("wishlistCardLine").value,
    operator: document.getElementById("wishlistOperator").value,
    target_price: document.getElementById("wishlistTarget").value,
    alert_enabled: document.getElementById("wishlistAlert").checked,
  };
  await performAndReload(wishlistId ? `/api/wishlist/${wishlistId}` : "/api/wishlist", { method: wishlistId ? "PATCH" : "POST", body: JSON.stringify(payload) }, "Wishlist saved");
}

async function deleteWishlist() {
  const wishlistId = document.getElementById("wishlistId").value;
  if (!wishlistId || !window.confirm("Delete this wishlist target?")) return;
  await performAndReload(`/api/wishlist/${wishlistId}`, { method: "DELETE" }, "Wishlist target deleted");
}

function setupRefresh() {
  const button = document.getElementById("refreshButton");
  button?.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await window.tcgApiFetch("/api/refresh", { method: "POST" });
      refreshActive = true;
      pollRefresh();
    } catch (error) {
      button.disabled = false;
      window.tcgToast(error.message, "error");
    }
  });
  checkExistingRefresh();
}

async function checkExistingRefresh() {
  try {
    const status = await window.tcgApiFetch("/api/refresh/status");
    if (["queued", "running"].includes(status.state)) {
      refreshActive = true;
      pollRefresh(status);
    }
  } catch (_) {
    // The status strip still shows persisted refresh information.
  }
}

async function pollRefresh(initial = null) {
  try {
    const status = initial || await window.tcgApiFetch("/api/refresh/status");
    renderRefreshStatus(status);
    if (["queued", "running"].includes(status.state)) {
      setTimeout(() => pollRefresh(), 1000);
    } else if (status.state === "complete" && refreshActive) {
      window.location.reload();
    } else if (status.state === "error") {
      document.getElementById("refreshButton").disabled = false;
      window.tcgToast(status.message || "Refresh failed", "error");
    }
  } catch (error) {
    document.getElementById("refreshButton").disabled = false;
    window.tcgToast(error.message, "error");
  }
}

function renderRefreshStatus(status) {
  const progress = document.getElementById("refreshProgress");
  const bar = document.getElementById("refreshProgressBar");
  const message = document.getElementById("refreshMessage");
  const button = document.getElementById("refreshButton");
  const running = ["queued", "running"].includes(status.state);
  progress.hidden = !running;
  button.disabled = running;
  button.textContent = running ? "Refreshing..." : "Refresh Prices";
  if (running) {
    const pct = status.total ? Math.round((status.current / status.total) * 100) : 2;
    bar.style.width = `${Math.max(2, pct)}%`;
    message.textContent = `${status.message || "Refreshing"} · ${status.current || 0} of ${status.total || 0}`;
  }
}

function setupDialogClosers() {
  document.querySelectorAll("[data-close-dialog]").forEach(button => button.addEventListener("click", () => button.closest("dialog")?.close()));
  document.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("click", event => {
    if (event.target === dialog) dialog.close();
  }));
}
