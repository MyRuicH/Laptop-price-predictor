import { ApiError, requestJSON, validPrediction } from "./api.js";
import { buildForm, clearFieldErrors, collectInput, FIELDS, setFieldError, validOptions } from "./form.js";
import { readLatest, saveLatest } from "./storage.js";

const CONFIG = window.APP_CONFIG;
const isAnalytics = document.body.dataset.page === "analytics";
const money = (value) => new Intl.NumberFormat("uk-UA", { style: "currency", currency: "UAH", maximumFractionDigits: 0 }).format(value);
const decimal = (value, digits = 2) => new Intl.NumberFormat("uk-UA", { maximumFractionDigits: digits }).format(value);
const dateTime = (value) => new Intl.DateTimeFormat("uk-UA", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Kyiv" }).format(new Date(value));
const node = (tag, className, text) => {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
};
function link(text, href, className = "button secondary") {
  const element = node("a", className, text); element.href = href; return element;
}
function metadata(list, title, value) {
  const row = node("div"); row.append(node("dt", "", title), node("dd", "", value)); list.append(row);
}
function navigateTo(id, focus = true) {
  const section = document.getElementById(id);
  if (!section) return;
  const target = section.querySelector("h2, h1") ?? section;
  if (focus) { target.tabIndex = -1; target.focus({ preventScroll: true }); }
  section.scrollIntoView({ behavior: !isAnalytics && document.documentElement.dataset.motion === "on" ? "smooth" : "instant", block: "start" });
}

function initShared() {
  document.querySelectorAll("[data-service-name]").forEach((element) => { element.textContent = CONFIG.serviceName; });
  const heroTitle = document.querySelector("[data-service-title]");
  if (heroTitle) {
    const words = CONFIG.serviceName.split(" ");
    const accent = node("span", "", words.pop());
    heroTitle.replaceChildren(document.createTextNode(words.join(" ")), node("br"), accent);
  }
  const routes = { "/": CONFIG.routes.prediction, "/analytics": CONFIG.routes.analytics, "/docs/": CONFIG.routes.swagger };
  document.querySelectorAll("a[href]").forEach((anchor) => {
    const [path, fragment] = anchor.getAttribute("href").split("#");
    if (routes[path]) anchor.setAttribute("href", `${routes[path]}${fragment === undefined ? "" : `#${fragment}`}`);
  });
  document.title = `${isAnalytics ? "Аналітика · " : ""}${CONFIG.serviceName}`;
  const themeToggle = document.querySelector(".theme-toggle");
  const themeOptions = document.getElementById("theme-options");
  const choices = [...themeOptions.querySelectorAll("button")];
  const motionToggle = document.querySelector(".motion-toggle");
  function syncPreferences() {
    const theme = document.documentElement.dataset.theme;
    const moving = document.documentElement.dataset.motion === "on";
    choices.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.themeChoice === theme)));
    const title = choices.find((button) => button.dataset.themeChoice === theme)?.childNodes[0]?.textContent;
    themeToggle.setAttribute("aria-label", `Обрати тему. Поточна: ${title}`);
    motionToggle.setAttribute("aria-pressed", String(moving));
    motionToggle.querySelector("[data-motion-label]").textContent = moving ? "Рух увімкнено" : "Рух вимкнено";
    motionToggle.querySelector(".motion-symbol").textContent = moving ? "Ⅱ" : "▷";
    if (isAnalytics) motionToggle.title = "Налаштування для головної сторінки. В аналітиці анімації завжди вимкнені.";
  }
  const closeThemes = () => { themeOptions.hidden = true; themeToggle.setAttribute("aria-expanded", "false"); };
  themeToggle.addEventListener("click", () => {
    themeOptions.hidden = !themeOptions.hidden;
    themeToggle.setAttribute("aria-expanded", String(!themeOptions.hidden));
    if (!themeOptions.hidden) choices.find((button) => button.getAttribute("aria-pressed") === "true")?.focus();
  });
  choices.forEach((button) => button.addEventListener("click", () => { window.SitePreferences.setTheme(button.dataset.themeChoice); syncPreferences(); closeThemes(); themeToggle.focus(); }));
  document.addEventListener("click", (event) => { if (!event.target.closest(".theme-control")) closeThemes(); });
  document.addEventListener("keydown", (event) => {
    if (themeOptions.hidden) return;
    if (event.key === "Escape") { closeThemes(); themeToggle.focus(); }
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const current = choices.indexOf(document.activeElement);
      const index = event.key === "Home" ? 0 : event.key === "End" ? choices.length - 1 : (current + (event.key === "ArrowDown" ? 1 : -1) + choices.length) % choices.length;
      choices[index].focus();
    }
  });
  themeOptions.addEventListener("focusout", (event) => { if (!event.relatedTarget?.closest(".theme-control")) closeThemes(); });
  motionToggle.addEventListener("click", () => { window.SitePreferences.setMotion(document.documentElement.dataset.motion !== "on"); syncPreferences(); });
  document.addEventListener("preferenceschange", syncPreferences);
  syncPreferences();

  document.querySelectorAll("[data-contact]").forEach((element) => {
    const field = element.dataset.contact;
    const value = CONFIG.contacts[field]?.trim();
    if (!value) return;
    element.textContent = value;
    let href;
    if (field === "email" && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) href = `mailto:${value}`;
    if (field === "phone" && /^\+?[\d\s()-]+$/.test(value)) href = `tel:${value.replace(/[^\d+]/g, "")}`;
    if (href) element.replaceChildren(link(value, href, ""));
  });
  function updateDate() {
    const today = new Date();
    const date = new Intl.DateTimeFormat("uk-UA", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Kyiv" }).format(today);
    const machineDate = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "Europe/Kyiv" }).format(today);
    document.querySelectorAll("[data-current-date]").forEach((element) => { element.textContent = date; element.dateTime = machineDate; });
  }
  updateDate(); setInterval(updateDate, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) updateDate(); });
  document.addEventListener("click", (event) => {
    const anchor = event.target.closest('a[href^="#"]');
    if (!anchor || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    const id = anchor.getAttribute("href").slice(1);
    if (!document.getElementById(id)) return;
    event.preventDefault(); history.replaceState(null, "", `#${id}`); navigateTo(id);
  });
}

function intervalExplanation(source) {
  if (source === "quantiles") return "Типовий діапазон за 10-м і 90-м квантилями відношення фактичної ціни до прогнозу на крос-валідації. Це емпірична оцінка, а не гарантія ціни.";
  if (source === "mape_fallback") return "Орієнтовний діапазон ±MAPE за тестовою вибіркою. Це запасний спосіб оцінки похибки, а не довірчий інтервал.";
  return "Типовий діапазон, розрахований сервером за похибками моделі. Це орієнтир, а не гарантія ціни чи довірчий інтервал.";
}

function summaryContent(snapshot, { analytics = false } = {}) {
  const { result, durationMs, createdAt, intervalSource } = snapshot;
  const fragment = document.createDocumentFragment();
  const summary = node("div", "prediction-summary");
  const price = node("div", "price-block");
  price.append(node("p", "price-caption", "Прогнозована ціна · останній успішний запит"), node("p", "price", money(result.predicted_price)), node("p", "price-interval", `${money(result.price_low)} — ${money(result.price_high)}`), node("p", "interval-explanation", intervalExplanation(intervalSource)));
  const meta = node("div", "result-meta"); const list = node("dl");
  metadata(list, "Модель", result.model_name);
  metadata(list, "Час HTTP-запиту в браузері", `${decimal(durationMs, 0)} мс`);
  metadata(list, "Час прогнозу · Київ", dateTime(createdAt));
  meta.append(list);
  if (!analytics) meta.append(link("Переглянути аналітику", `${CONFIG.routes.analytics}#latest`, "button primary"));
  summary.append(price, meta); fragment.append(summary);
  if (result.warnings.length) {
    const warnings = node("div", "warning-list"); warnings.append(node("h3", "", "Зверніть увагу"));
    const ul = node("ul"); result.warnings.forEach((warning) => ul.append(node("li", "", warning))); warnings.append(ul); fragment.append(warnings);
  }
  return fragment;
}

function issueMessage(issue) {
  const field = FIELDS.find((item) => issue.loc.includes(item.key));
  const messages = {
    missing: "Заповніть це поле.", int_parsing: "Вкажіть ціле число.", int_from_float: "Вкажіть ціле число.", float_parsing: "Вкажіть коректне число.",
    greater_than_equal: field ? `Мінімальне значення: ${decimal(field.min)}.` : "Значення нижче допустимого.",
    less_than_equal: field ? `Максимальне значення: ${decimal(field.max)}.` : "Значення вище допустимого.",
    string_too_short: "Значення не може бути порожнім.", extra_forbidden: "Сервер не приймає це поле.",
  };
  return { key: field?.key ?? (issue.msg.includes("screen_height") ? "screen_height" : null), message: messages[issue.type] ?? issue.msg };
}

async function initPrediction() {
  const form = document.getElementById("laptop-form");
  const fieldset = document.getElementById("specification-fields");
  const submit = document.getElementById("predict-button");
  const clear = document.getElementById("clear-form");
  const optionsStatus = document.getElementById("options-status");
  const retryOptions = document.getElementById("retry-options");
  const resultContainer = document.getElementById("prediction-result");
  const toast = document.querySelector(".error-toast");
  const validationSummary = document.getElementById("validation-summary");
  let options = null; let busy = false; let loadingOptions = false; let intervalSource = null;
  document.querySelector(".toast-close").addEventListener("click", () => { toast.hidden = true; });

  // Джерело діапазону необов’язкове для прогнозу: межі завжди беремо з predict.
  requestJSON(CONFIG.routes.modelInfo).then((info) => { intervalSource = info.interval_source; }).catch(() => {});
  async function loadOptions() {
    if (loadingOptions) return;
    loadingOptions = true; fieldset.disabled = true; submit.disabled = true; clear.disabled = true;
    form.setAttribute("aria-busy", "true"); retryOptions.hidden = true;
    optionsStatus.hidden = false; optionsStatus.dataset.state = "loading"; optionsStatus.textContent = "Завантажуємо доступні характеристики…";
    try {
      const data = await requestJSON(CONFIG.routes.options);
      if (!validOptions(data)) throw new ApiError("Довідник має неповний або несумісний формат.", { kind: "format" });
      buildForm(document.getElementById("form-groups"), data); options = data;
      fieldset.disabled = false; submit.disabled = false; clear.disabled = false;
      optionsStatus.textContent = "Характеристики завантажено. Поля зі знаком * обов’язкові.";
      optionsStatus.hidden = true;
    } catch (error) {
      optionsStatus.dataset.state = "error";
      optionsStatus.textContent = `Не вдалося завантажити характеристики. ${error.message}`;
      retryOptions.hidden = false;
    } finally { form.setAttribute("aria-busy", "false"); loadingOptions = false; }
  }
  retryOptions.addEventListener("click", loadOptions);
  clear.addEventListener("click", () => { if (busy) return; form.reset(); clearFieldErrors(form); toast.hidden = true; form.elements.namedItem("company")?.focus(); });
  form.addEventListener("input", (event) => {
    const control = event.target;
    control.removeAttribute("aria-invalid");
    const error = document.getElementById(`${control.name}-error`); if (error) { error.hidden = true; error.textContent = ""; }
    validationSummary.hidden = true;
  });

  function renderError(error) {
    const panel = node("div", "error-details"); panel.append(node("h3", "", "Не вдалося отримати прогноз"), node("p", "", error.message));
    const http = error.kind === "client" ? "Помилка обробки відповіді в браузері; код сервера не визначено." : error.status == null ? "HTTP-відповідь не отримана; код сервера відсутній." : `HTTP ${error.status}`;
    panel.append(node("p", "section-disclaimer", http));
    if (error.code) panel.append(node("p", "", `Код помилки: ${error.code}`));
    if (error.issues?.length) {
      const list = node("ul");
      error.issues.forEach((issue) => {
        const { key, message } = issueMessage(issue);
        const label = FIELDS.find((field) => field.key === key)?.label;
        const suffix = issue.type ? ` (${issue.type})` : "";
        list.append(node("li", "", `${label ? `${label}: ` : ""}${message}${suffix}`));
        if (key) setFieldError(form, key, message);
      });
      panel.append(list);
    }
    const actions = node("div", "error-actions"); actions.append(link("До форми", "#specifications"));
    if (error.status !== 422) {
      const retry = node("button", "button primary", "Спробувати ще раз"); retry.type = "button"; retry.addEventListener("click", () => form.requestSubmit()); actions.append(retry);
    }
    panel.append(actions); resultContainer.replaceChildren(panel);
    toast.querySelector("[data-toast-message]").textContent = error.message; toast.hidden = false;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault(); if (busy || !options) return;
    clearFieldErrors(form); toast.hidden = true;
    const { payload, errors } = collectInput(form, options);
    if (errors.length) {
      errors.forEach(({ key, message }) => setFieldError(form, key, message));
      validationSummary.textContent = "Перевірте позначені поля. Запит ще не надіслано."; validationSummary.hidden = false;
      form.querySelector('[aria-invalid="true"]')?.focus(); return;
    }
    busy = true; submit.disabled = true; clear.disabled = true; fieldset.disabled = true;
    submit.textContent = "Обчислюємо…"; form.setAttribute("aria-busy", "true"); resultContainer.setAttribute("aria-busy", "true");
    const pending = node("div", "pending-state"); pending.append(node("span", "pending-mark", "◇"), node("h3", "", "Обчислюємо новий прогноз…"), node("p", "", "Характеристики надіслано моделі. Очікуємо відповідь сервера.")); resultContainer.replaceChildren(pending);
    const started = performance.now();
    try {
      const result = await requestJSON(CONFIG.routes.predict, { method: "POST", body: payload });
      const durationMs = performance.now() - started;
      if (!validPrediction(result)) throw new ApiError("Сервер повернув несумісний формат прогнозу. Спробуйте ще раз.", { status: 200, kind: "format" });
      const snapshot = { input: payload, result, durationMs, createdAt: new Date().toISOString(), intervalSource };
      const saved = saveLatest(snapshot);
      resultContainer.replaceChildren(summaryContent(snapshot));
      if (!saved) resultContainer.append(node("p", "info-note", "Браузер не дозволив зберегти прогноз у цій вкладці. Після переходу в аналітику він може бути недоступний."));
      navigateTo("result");
    } catch (error) {
      renderError(error instanceof ApiError ? error : new ApiError("Не вдалося обробити прогноз. Спробуйте ще раз.", { kind: "client" }));
    } finally {
      busy = false; submit.disabled = false; clear.disabled = false; fieldset.disabled = false; submit.textContent = "Прогноз";
      form.setAttribute("aria-busy", "false"); resultContainer.setAttribute("aria-busy", "false");
    }
  });

  if ("IntersectionObserver" in window) {
    const card = document.querySelector(".form-card");
    const observer = new IntersectionObserver((entries) => { if (entries.some((entry) => entry.isIntersecting)) { card.classList.add("revealed"); observer.disconnect(); } }, { threshold: .05 }); observer.observe(card);
  }
  await loadOptions();
}

function renderModelInfo(info, container) {
  if (!info || typeof info.best_model_name !== "string" || !info.test_metrics || typeof info.cv_results !== "object") throw new ApiError("Метрики мають несумісний формат.", { kind: "format" });
  const fragment = document.createDocumentFragment();
  const banner = node("div", "model-banner");
  banner.append(node("p", "eyebrow", "Активна модель прогнозу"), node("h3", "", info.best_model_name));
  const descriptions = { HistGradientBoosting: "Гістограмний градієнтний бустинг послідовно навчає дерева, які уточнюють попередні оцінки.", RandomForest: "Випадковий ліс усереднює прогнози багатьох дерев.", LinearRegression: "Лінійна регресія моделює залежність ціни від закодованих характеристик.", Dummy: "Базовий алгоритм без використання характеристик для порівняння якості." };
  if (descriptions[info.best_model_name]) banner.append(node("p", "", descriptions[info.best_model_name]));
  if (Number.isInteger(info.n_features)) banner.append(node("p", "", `Вхідних ознак моделі: ${info.n_features}. Бренди процесора й графіки та їхню пару сервер визначає автоматично.`));
  fragment.append(banner);
  const metrics = node("dl", "metric-grid");
  for (const [key, label, format] of [["rmse", "RMSE · грн", money], ["mae", "MAE · грн", money], ["r2", "R² · без одиниць", (value) => decimal(value, 3)], ["mape", "MAPE · %", (value) => `${decimal(value * 100)} %`]]) {
    const value = info.test_metrics[key];
    if (typeof value !== "number" || !Number.isFinite(value)) continue;
    const metric = node("div", "metric-card panel"); metric.append(node("dt", "", label), node("dd", "", format(value))); metrics.append(metric);
  }
  fragment.append(metrics, node("p", "metric-help", "Метрики на тестовій вибірці. MAE — середня абсолютна похибка; RMSE сильніше враховує великі помилки; R² характеризує пояснену варіацію; MAPE — середня абсолютна відносна похибка. Це загальні показники, не похибка вашого ноутбука."));
  const wrap = node("div", "table-wrap"); wrap.tabIndex = 0; wrap.setAttribute("role", "region"); wrap.setAttribute("aria-label", "Результати експериментів із моделями");
  const table = node("table"); table.append(node("caption", "", "Крос-валідація до тюнінгу та результати підбору параметрів. У сервісі доступний один прогноз активної моделі."));
  const head = node("thead"); const header = node("tr");
  ["Модель", "CV RMSE ± std, грн", "Після тюнінгу, грн"].forEach((label) => { const th = node("th", "", label); th.scope = "col"; header.append(th); }); head.append(header); table.append(head);
  const body = node("tbody");
  for (const [name, values] of Object.entries(info.cv_results)) {
    if (!values || !Number.isFinite(values.cv_rmse_mean) || !Number.isFinite(values.cv_rmse_std)) continue;
    const row = node("tr"); const nameCell = node("td", "", name);
    if (descriptions[name]) nameCell.append(node("p", "field-hint", descriptions[name]));
    row.append(nameCell, node("td", "", `${decimal(values.cv_rmse_mean)} ± ${decimal(values.cv_rmse_std)}`));
    const tuned = info.tuning?.[name]?.cv_rmse;
    row.append(node("td", "", typeof tuned === "number" && Number.isFinite(tuned) ? decimal(tuned) : "Не надано")); body.append(row);
  }
  table.append(body); wrap.append(table); fragment.append(wrap, node("p", "info-note", intervalExplanation(info.interval_source)));
  container.replaceChildren(fragment);
}

async function initAnalytics() {
  const latest = readLatest();
  if (latest) {
    document.getElementById("latest").hidden = false; document.getElementById("latest-link").hidden = false;
    document.getElementById("latest-summary").replaceChildren(summaryContent(latest, { analytics: true }));
    const specifications = document.getElementById("latest-specifications");
    FIELDS.forEach((field) => {
      const value = latest.input[field.key];
      metadata(specifications, field.label, value == null ? "Не вказано" : typeof value === "boolean" ? value ? "Так" : "Ні" : String(value));
    });
  }
  let loading = false;
  const status = document.getElementById("model-status");
  const retry = document.getElementById("retry-model-info");
  const infoContainer = document.getElementById("model-info");
  async function loadModelInfo() {
    if (loading) return;
    loading = true; status.hidden = false; status.dataset.state = "loading"; status.textContent = "Завантажуємо метрики моделі…"; retry.hidden = true;
    try {
      const info = await requestJSON(CONFIG.routes.modelInfo);
      renderModelInfo(info, infoContainer); infoContainer.hidden = false; status.hidden = true;
      if (latest && !latest.intervalSource) document.getElementById("latest-summary").replaceChildren(summaryContent({ ...latest, intervalSource: info.interval_source }, { analytics: true }));
    } catch (error) { status.dataset.state = "error"; status.textContent = `Метрики наразі недоступні. ${error.message}`; retry.hidden = false; }
    finally { loading = false; }
  }
  retry.addEventListener("click", loadModelInfo);
  document.querySelectorAll(".chart-card img").forEach((img) => {
    const missing = () => { img.closest("a").replaceWith(node("p", "chart-missing", "Зображення недоступне. Перевірте наявність файлу графіка на сервері.")); };
    img.addEventListener("error", missing, { once: true });
    if (img.complete && img.naturalWidth === 0) missing();
  });
  const contentsLinks = [...document.querySelectorAll(".analytics-contents nav a")];
  function updateContents() {
    const offset = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--header-height")) + 60;
    const sections = [...document.querySelectorAll(".analytics-sections > section:not([hidden])")];
    let active = sections[0];
    sections.forEach((section) => { if (section.getBoundingClientRect().top <= offset) active = section; });
    contentsLinks.forEach((anchor) => { if (anchor.hash === `#${active?.id}`) anchor.setAttribute("aria-current", "location"); else anchor.removeAttribute("aria-current"); });
  }
  window.addEventListener("scroll", updateContents, { passive: true });
  window.addEventListener("resize", updateContents); updateContents();
  if (location.hash === "#latest" && latest) requestAnimationFrame(() => navigateTo("latest"));
  await loadModelInfo();
  // Метрики змінюють висоту сторінки; повторно вирівнюємо пряме якірне посилання.
  if (location.hash && document.getElementById(location.hash.slice(1)) && !document.getElementById(location.hash.slice(1)).hidden) navigateTo(location.hash.slice(1), false);
}

initShared();
if (isAnalytics) initAnalytics(); else initPrediction();
