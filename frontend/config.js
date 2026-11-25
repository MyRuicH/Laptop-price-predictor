/* Єдине місце для назви сервісу, контактів, маршрутів і налаштувань. */
window.APP_CONFIG = Object.freeze({
  serviceName: "Прогноз ціни ноутбука",
  contacts: { author: "Ожиховький Максим Віталійович", group: "ФЕІ-24с", email: "maksimozihovskij@gmail.com", phone: "+380 (96) 493 55"},
  routes: { prediction: "/", analytics: "/analytics", swagger: "/docs/", options: "/api/options", predict: "/api/predict", modelInfo: "/api/model-info" },
  themes: ["dark", "light", "purple"],
  storageKeys: { theme: "laptop.theme", motion: "laptop.motion", latest: "laptop.latest.v1" },
  // Перший прогноз включає підготовку ознак; тайм-аут не залишає UI в очікуванні.
  requestTimeoutMs: 30000,
});
