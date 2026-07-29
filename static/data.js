let importRows = [];

window.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupTransactions();
  setupNotifications();
  setupHistoryRepair();
  setupImport();
  setupRestore();
  setupDialogClosers();
});

function setupTabs() {
  document.querySelectorAll("[data-tab]").forEach(button => button.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach(item => item.classList.toggle("active", item === button));
    document.querySelectorAll("[data-tab-panel]").forEach(panel => { panel.hidden = panel.dataset.tabPanel !== button.dataset.tab; });
  }));
}

function setupTransactions() {
  const dialog = document.getElementById("transactionDialog");
  document.getElementById("addTransactionButton")?.addEventListener("click", () => dialog.showModal());
  document.getElementById("transactionForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    const type = document.getElementById("transactionType").value;
    const amount = Number(document.getElementById("transactionAmount").value);
    const payload = {
      type,
      game: document.getElementById("transactionGame").value,
      name: document.getElementById("transactionName").value,
      quantity: Number(document.getElementById("transactionQuantity").value || 1),
      notes: document.getElementById("transactionNotes").value,
      total_amount: type === "purchase" ? amount : null,
      net_amount: type === "sale" ? amount : null,
      adjustment_amount: type === "adjustment" ? amount : null,
    };
    try {
      await window.tcgApiFetch("/api/transactions", { method: "POST", body: JSON.stringify(payload) });
      window.tcgToast("Transaction recorded", "success");
      setTimeout(() => window.location.reload(), 400);
    } catch (error) { window.tcgToast(error.message, "error"); }
  });
}

function setupNotifications() {
  document.getElementById("testDiscordButton")?.addEventListener("click", async event => {
    event.currentTarget.disabled = true;
    try {
      const data = await window.tcgApiFetch("/api/notifications/test", { method: "POST" });
      window.tcgToast(data.message, "success");
    } catch (error) { window.tcgToast(error.message, "error"); }
    finally { event.currentTarget.disabled = false; }
  });
}

function setupHistoryRepair() {
  document.querySelectorAll(".edit-history").forEach(button => button.addEventListener("click", async () => {
    const row = button.closest("[data-history-day]");
    const value = window.prompt(`Correct value for ${row.dataset.historyDay}`, button.dataset.value);
    if (value == null) return;
    try {
      await window.tcgApiFetch(`/api/history/${row.dataset.historyDay}`, { method: "PATCH", body: JSON.stringify({ value }) });
      window.tcgToast("History point corrected", "success");
      setTimeout(() => window.location.reload(), 400);
    } catch (error) { window.tcgToast(error.message, "error"); }
  }));
  document.querySelectorAll(".remove-history").forEach(button => button.addEventListener("click", async () => {
    const row = button.closest("[data-history-day]");
    if (!window.confirm(`Exclude the ${row.dataset.historyDay} history point?`)) return;
    try {
      await window.tcgApiFetch(`/api/history/${row.dataset.historyDay}`, { method: "DELETE" });
      row.remove();
      window.tcgToast("History point excluded", "success");
    } catch (error) { window.tcgToast(error.message, "error"); }
  }));
}

function setupImport() {
  document.getElementById("importForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    const file = document.getElementById("importFile").files[0];
    if (!file) return;
    const body = new FormData();
    body.append("file", file);
    try {
      const data = await window.tcgApiFetch("/api/import/preview", { method: "POST", body });
      importRows = data.rows;
      renderImportPreview(data);
    } catch (error) { window.tcgToast(error.message, "error"); }
  });
}

function renderImportPreview(data) {
  const target = document.getElementById("importPreview");
  const sample = data.rows.slice(0, 12);
  target.innerHTML = `
    <div class="import-summary"><strong>${data.valid} ready</strong><span>${data.invalid} need attention</span></div>
    <div class="data-table-wrap"><table class="data-table"><thead><tr><th>Row</th><th>Game</th><th>Card</th><th>Qty</th><th>Status</th></tr></thead><tbody>
      ${sample.map(row => `<tr><td>${row.row}</td><td>${window.tcgEscape(row.game)}</td><td>${window.tcgEscape(row.card_line)}</td><td>${row.quantity}</td><td class="${row.valid ? "positive" : "negative"}">${row.valid ? "Ready" : window.tcgEscape(row.errors.join(", "))}</td></tr>`).join("")}
    </tbody></table></div>
    ${data.rows.length > sample.length ? `<p class="muted">Showing ${sample.length} of ${data.rows.length} rows.</p>` : ""}
    <button class="button" id="commitImportButton" type="button" ${data.valid ? "" : "disabled"}>Import ${data.valid} Cards</button>`;
  document.getElementById("commitImportButton")?.addEventListener("click", commitImport);
}

async function commitImport(event) {
  event.currentTarget.disabled = true;
  try {
    const data = await window.tcgApiFetch("/api/import/commit", { method: "POST", body: JSON.stringify({ rows: importRows }) });
    window.tcgToast(`${data.added} added, ${data.duplicate} duplicates skipped`, "success");
    setTimeout(() => window.location.href = "/", 700);
  } catch (error) {
    event.currentTarget.disabled = false;
    window.tcgToast(error.message, "error");
  }
}

function setupRestore() {
  document.getElementById("restoreForm")?.addEventListener("submit", async event => {
    event.preventDefault();
    const file = document.getElementById("restoreFile").files[0];
    if (!file || !window.confirm("Restore this backup and replace matching tracker data files?")) return;
    const body = new FormData();
    body.append("file", file);
    try {
      const data = await window.tcgApiFetch("/api/backup/restore", { method: "POST", body });
      window.tcgToast(`Restored ${data.files.length} files`, "success");
      setTimeout(() => window.location.href = "/", 700);
    } catch (error) { window.tcgToast(error.message, "error"); }
  });
}

function setupDialogClosers() {
  document.querySelectorAll("[data-close-dialog]").forEach(button => button.addEventListener("click", () => button.closest("dialog")?.close()));
  document.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); }));
}
