window.addEventListener("DOMContentLoaded", () => {
  setupChart();
  setupCollectionTools();
  setupRefresh();
});

function setupChart() {
  const canvas = document.getElementById("valueChart");
  const dataNode = document.getElementById("historyData");
  if (!canvas || !dataNode || !window.Chart) return;

  const allRows = JSON.parse(dataNode.textContent || "[]");
  let activeRows = allRows;
  let theme = chartTheme();
  const chart = new Chart(canvas, {
    type: "line",
    data: chartData(activeRows, theme),
    options: chartOptions(theme),
  });

  document.querySelectorAll("[data-days]").forEach(button => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-days]").forEach(item => item.classList.remove("active"));
      button.classList.add("active");
      const days = Number(button.dataset.days || 0);
      activeRows = filterRows(allRows, days);
      chart.data = chartData(activeRows, chartTheme());
      chart.update();
    });
  });

  window.addEventListener("themechange", () => {
    theme = chartTheme();
    chart.data = chartData(activeRows, theme);
    chart.options = chartOptions(theme);
    chart.update();
  });
}

function chartData(rows, theme) {
  return {
    labels: rows.map(row => row.date),
    datasets: [
      {
        label: "Collection Value",
        data: rows.map(row => row.value),
        borderColor: theme.line,
        backgroundColor: theme.fill,
        borderWidth: 2,
        fill: true,
        tension: 0.25,
        pointRadius: 0,
      },
    ],
  };
}

function chartOptions(theme) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: "index" },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: theme.tooltipBg,
        titleColor: theme.text,
        bodyColor: theme.text,
        borderColor: theme.grid,
        borderWidth: 1,
      },
    },
    scales: {
      x: {
        grid: { color: theme.grid },
        ticks: { color: theme.tick, maxTicksLimit: 6 },
      },
      y: {
        beginAtZero: false,
        grid: { color: theme.grid },
        ticks: { color: theme.tick, callback: value => `$${value}` },
      },
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
  const last = new Date(rows[rows.length - 1].date);
  const cutoff = new Date(last);
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
      const matchesName = !term || card.dataset.name.includes(term);
      const matchesGame = gameValue === "all" || card.dataset.game === gameValue;
      card.hidden = !(matchesName && matchesGame);
    });

    const visibleCards = cards.filter(card => !card.hidden);
    visibleCards.sort((a, b) => compareCards(a, b, sortValue));
    visibleCards.forEach(card => list.appendChild(card));
  };

  [search, game, sort].forEach(control => control?.addEventListener("input", apply));
}

function compareCards(a, b, sortValue) {
  if (sortValue === "name") return a.dataset.name.localeCompare(b.dataset.name);
  if (sortValue === "game") return a.dataset.game.localeCompare(b.dataset.game);
  if (sortValue === "unpriced") return a.dataset.priced.localeCompare(b.dataset.priced);
  return Number(b.dataset.value || 0) - Number(a.dataset.value || 0);
}

function setupRefresh() {
  const button = document.getElementById("refreshButton");
  if (!button) return;

  button.addEventListener("click", async () => {
    button.disabled = true;
    button.textContent = "Refreshing...";
    try {
      const response = await fetch("/api/refresh", { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Refresh failed");
      window.location.reload();
    } catch (error) {
      button.textContent = error.message;
      setTimeout(() => {
        button.disabled = false;
        button.textContent = "Refresh Prices";
      }, 3000);
    }
  });
}
