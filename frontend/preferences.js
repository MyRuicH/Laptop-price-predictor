/* Виконується в head до першого відображення, щоб зберегти обрану тему. */
(() => {
  const config = window.APP_CONFIG;
  const read = (key) => { try { return localStorage.getItem(key); } catch { return null; } };
  const write = (key, value) => { try { localStorage.setItem(key, value); } catch { /* Сховище може бути заблоковане. */ } };
  const storedTheme = read(config.storageKeys.theme);
  const storedMotion = read(config.storageKeys.motion);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let explicitMotion = storedMotion === "on" || storedMotion === "off";
  document.documentElement.dataset.theme = config.themes.includes(storedTheme) ? storedTheme : "dark";
  document.documentElement.dataset.motion = explicitMotion ? storedMotion : reducedMotion.matches ? "off" : "on";
  window.SitePreferences = {
    setTheme(theme) {
      if (!config.themes.includes(theme)) return;
      document.documentElement.dataset.theme = theme;
      write(config.storageKeys.theme, theme);
    },
    setMotion(enabled) {
      explicitMotion = true;
      document.documentElement.dataset.motion = enabled ? "on" : "off";
      write(config.storageKeys.motion, enabled ? "on" : "off");
    },
  };
  reducedMotion.addEventListener("change", (event) => {
    if (!explicitMotion) {
      document.documentElement.dataset.motion = event.matches ? "off" : "on";
      document.dispatchEvent(new Event("preferenceschange"));
    }
  });
})();
