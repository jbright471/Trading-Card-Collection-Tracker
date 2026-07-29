window.tcgApiFetch = async function tcgApiFetch(url, options = {}) {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (options.method && !["GET", "HEAD"].includes(options.method.toUpperCase())) {
    headers.set("X-CSRF-Token", csrf);
  }
  const response = await fetch(url, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401 && data.login_url) {
    window.location.href = `${data.login_url}?next=${encodeURIComponent(window.location.pathname)}`;
    throw new Error("Tracker is locked");
  }
  if (!response.ok) throw new Error(data.error || data.message || "Request failed");
  return data;
};

window.tcgMoney = function tcgMoney(value, currency = "USD") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "N/A";
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(number);
  } catch (_) {
    return `${currency} ${number.toFixed(2)}`;
  }
};

window.tcgToast = function tcgToast(message, kind = "info") {
  const toast = document.getElementById("globalToast");
  if (!toast) return;
  toast.textContent = message;
  toast.dataset.kind = kind;
  toast.classList.add("show");
  clearTimeout(window.__tcgToastTimer);
  window.__tcgToastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
};

window.tcgEscape = function tcgEscape(value) {
  const node = document.createElement("div");
  node.textContent = value == null ? "" : String(value);
  return node.innerHTML;
};

window.tcgEscapeAttr = function tcgEscapeAttr(value) {
  return window.tcgEscape(value).replaceAll('"', "&quot;").replaceAll("'", "&#39;");
};
