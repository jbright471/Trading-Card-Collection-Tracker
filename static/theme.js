const THEME_KEY = "tcg-theme";

window.addEventListener("DOMContentLoaded", () => {
  const button = document.getElementById("themeToggle");
  if (!button) return;

  const applyTheme = theme => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
    button.setAttribute("aria-pressed", String(theme === "dark"));
    button.querySelector(".theme-toggle-label").textContent = theme === "dark" ? "Dark" : "Light";
    window.dispatchEvent(new CustomEvent("themechange", { detail: { theme } }));
  };

  const currentTheme = document.documentElement.dataset.theme || "light";
  applyTheme(currentTheme);

  button.addEventListener("click", () => {
    const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
  });
});
