// OrcaFind theme toggle (light/dark) shared across pages.
// - Default: system preference
// - Persist: localStorage key "orcafind_theme"
// - Apply early via inline <script> in <head> (to avoid flash)

(function () {
  const STORAGE_KEY = "orcafind_theme";

  function getPreferredTheme() {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === "light" || saved === "dark") return saved;
    } catch (_err) {}

    const prefersDark = !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    return prefersDark ? "dark" : "light";
  }

  function applyTheme(theme) {
    const next = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    // Helps native form controls match.
    document.documentElement.style.colorScheme = next;
    updateToggleUI();
  }

  function updateToggleUI() {
    const theme = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    const toggles = document.querySelectorAll("[data-theme-toggle]");
    toggles.forEach((btn) => {
      const label = theme === "dark" ? "Light" : "Dark";
      btn.setAttribute("aria-label", `Switch to ${label} mode`);
    });
  }

  function toggleTheme() {
    const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    const next = current === "dark" ? "light" : "dark";
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch (_err) {}
    applyTheme(next);
  }

  // Expose for inline onclick handlers if needed.
  window.toggleTheme = toggleTheme;
  window.applyTheme = applyTheme;

  // Initialize after DOM is available so we can update button labels.
  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(getPreferredTheme());
  });
})();
