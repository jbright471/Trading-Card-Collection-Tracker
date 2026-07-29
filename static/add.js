let selectedCard = null;
let debounceTimer = null;

window.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("searchInput");
  const searchGame = document.getElementById("searchGame");
  const form = document.getElementById("addForm");
  const backButton = document.getElementById("backToResults");

  searchInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(runSearch, 300);
  });
  searchGame.addEventListener("change", () => {
    if (searchInput.value.trim()) runSearch();
  });
  form.addEventListener("submit", addSelectedCard);
  document.getElementById("watchSelected").addEventListener("click", () => {
    document.getElementById("quickWishlist").hidden = false;
    document.getElementById("quickTarget").focus();
  });
  document.getElementById("saveQuickWishlist").addEventListener("click", addSelectedWishlist);
  backButton.addEventListener("click", () => {
    document.getElementById("addLayout").classList.remove("show-detail");
  });
});

async function runSearch() {
  const input = document.getElementById("searchInput");
  const game = document.getElementById("searchGame").value;
  const results = document.getElementById("searchResults");
  const query = input.value.trim();

  if (!query) {
    results.innerHTML = emptyState("Search for a card", "Choose a game, search, then add it.");
    return;
  }

  results.innerHTML = emptyState("Searching...", "Checking card databases.");
  try {
    const data = await window.tcgApiFetch(`/api/search/${game.toLowerCase()}?q=${encodeURIComponent(query)}`);
    renderResults(Array.isArray(data) ? data : []);
  } catch (error) {
    results.innerHTML = emptyState("Search failed", error.message);
  }
}

function renderResults(cards) {
  const results = document.getElementById("searchResults");
  if (cards.length === 0) {
    results.innerHTML = emptyState("No matches", "Try a different name or set.");
    return;
  }

  results.innerHTML = "";
  cards.forEach((card, index) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "result-item";
    row.dataset.index = index;
    row.innerHTML = `
      ${card.image ? `<img src="${window.tcgEscapeAttr(card.image)}" alt="">` : '<span class="image-placeholder">Card</span>'}
      <span>
        <h3>${escapeHtml(card.name)}</h3>
        <p>${escapeHtml(card.set || "Set unknown")}</p>
      </span>
      <span>
        <strong>${formatPrice(card.price)}</strong>
        <span class="badge badge-${window.tcgEscapeAttr(card.game)}">${escapeHtml(card.game)}</span>
      </span>
    `;
    row.addEventListener("click", () => selectCard(card, row));
    results.appendChild(row);
  });
}

function selectCard(card, row) {
  selectedCard = card;
  document.querySelectorAll(".result-item").forEach(item => item.classList.remove("selected"));
  row.classList.add("selected");

  const selected = document.getElementById("selectedCard");
  selected.className = "selected-card";
  selected.innerHTML = `
    ${card.image ? `<img class="selected-preview" src="${window.tcgEscapeAttr(card.image)}" alt="${window.tcgEscapeAttr(card.name)}">` : '<div class="preview-placeholder">No Image</div>'}
    <div class="selected-copy">
      <h1>${escapeHtml(card.name)}</h1>
      <p class="muted">${escapeHtml(card.set || "Set unknown")} · ${escapeHtml(card.game)}</p>
      <p class="muted">Current market: ${window.tcgMoney(card.price, card.currency || "USD")}</p>
      <p class="muted">${escapeHtml(card.source || "Market source")}${card.price_finish ? ` · ${escapeHtml(card.price_finish)}` : ""}</p>
    </div>
  `;
  const availableFinishes = new Set(card.finishes || ["regular"]);
  document.querySelectorAll('input[name="finish"]').forEach(input => {
    input.disabled = !availableFinishes.has(input.value);
    input.closest("label").classList.toggle("disabled", input.disabled);
  });
  const preferred = document.querySelector('input[name="finish"]:not(:disabled)');
  if (!document.querySelector('input[name="finish"]:checked:not(:disabled)') && preferred) preferred.checked = true;
  document.getElementById("addForm").hidden = false;
  document.getElementById("addLayout").classList.add("show-detail");
}

async function addSelectedCard(event) {
  event.preventDefault();
  if (!selectedCard) return;

  const button = document.getElementById("submitAdd");
  button.disabled = true;
  button.textContent = "Adding...";

  const finish = document.querySelector('input[name="finish"]:checked')?.value || "regular";
  const payload = {
    game: selectedCard.game,
    card_line: selectedCard.card_line || selectedCard.name,
    finish,
    condition: document.getElementById("conditionInput").value,
    buy_price: document.getElementById("buyPriceInput").value.trim(),
    quantity: document.getElementById("quantityInput").value || 1,
  };

  try {
    const data = await window.tcgApiFetch("/api/add-card", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    showToast(data.status === "duplicate" ? "Already tracked." : "Added to collection. Refresh when ready to price it.");
    button.textContent = "Add to Collection";
    document.getElementById("quantityInput").value = "1";
    document.getElementById("buyPriceInput").value = "";
  } catch (error) {
    showToast(error.message);
    button.textContent = "Add to Collection";
  } finally {
    button.disabled = false;
  }
}

async function addSelectedWishlist() {
  if (!selectedCard) return;
  const target = document.getElementById("quickTarget").value;
  if (target === "") {
    showToast("Enter a target price.");
    return;
  }
  try {
    const data = await window.tcgApiFetch("/api/wishlist", {
      method: "POST",
      body: JSON.stringify({
        game: selectedCard.game,
        card_line: selectedCard.card_line || selectedCard.name,
        operator: document.getElementById("quickOperator").value,
        target_price: target,
        alert_enabled: true,
      }),
    });
    showToast(data.status === "duplicate" ? "Already on the wishlist." : "Wishlist target saved.");
    document.getElementById("quickWishlist").hidden = true;
    document.getElementById("quickTarget").value = "";
  } catch (error) {
    showToast(error.message);
  }
}

function emptyState(title, message) {
  return `<div class="empty-state compact"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p></div>`;
}

function formatPrice(price) {
  const value = Number(price);
  return Number.isFinite(value) ? `$${value.toFixed(2)}` : "N/A";
}

function showToast(message) {
  window.tcgToast(message);
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value || "";
  return div.innerHTML;
}
