/* Межі та обов’язковість звірені з backend/schemas.py; категорії надходять з API. */
export const GROUPS = [
  { title: "Загальні характеристики", icon: "▣", fields: [
    { key: "company", label: "Бренд", source: "company", required: true },
    { key: "type_name", label: "Тип ноутбука", source: "type_name", required: true },
    { key: "opsys", label: "Операційна система", source: "opsys", hint: "Не обрано — сервер використає типове значення. No OS означає відсутність ОС." },
    { key: "weight", label: "Вага, кг", type: "number", min: 0.5, max: 6, required: true, placeholder: "Наприклад, 1.8" },
  ] },
  { title: "Процесор та графіка", icon: "◇", fields: [
    { key: "cpu_model", label: "Модель процесора", source: "cpu_models", required: true },
    { key: "cpu_ghz", label: "Частота процесора, ГГц", type: "number", min: 0.8, max: 4, required: true, placeholder: "Наприклад, 2.5" },
    { key: "gpu_model", label: "Модель відеокарти", source: "gpu_models", required: true },
  ] },
  { title: "Пам’ять та накопичувач", icon: "▤", fields: [
    { key: "ram_gb", label: "Оперативна пам’ять, ГБ", source: "ram_gb", numeric: true, min: 1, max: 64, required: true },
    { key: "storage_type", label: "Тип накопичувача", source: "storage_type", required: true },
    { key: "storage_gb", label: "Обсяг накопичувача, ГБ", type: "number", integer: true, min: 8, max: 2000, required: true, placeholder: "Наприклад, 512", hint: "Вкажіть перший накопичувач. 1 ТБ = 1000 ГБ; обсяги двох дисків не додаються." },
  ] },
  { title: "Екран", icon: "▱", fields: [
    { key: "inches", label: "Діагональ, дюйми", type: "number", min: 10, max: 20, required: true, placeholder: "Наприклад, 15.6" },
    { key: "screen_width", label: "Ширина екрана, px", source: "screen_width", numeric: true, min: 1366, max: 3840, required: true },
    { key: "screen_height", label: "Висота екрана, px", source: "screen_height", numeric: true, min: 768, max: 2160, hint: "Лише для перевірки роздільності; модель не використовує висоту." },
    { key: "is_ips", label: "IPS-матриця", type: "checkbox" },
    { key: "is_touchscreen", label: "Сенсорний екран", type: "checkbox" },
  ] },
];
export const FIELDS = GROUPS.flatMap((group) => group.fields);
const number = (value) => new Intl.NumberFormat("uk-UA", { maximumFractionDigits: value !== 0 && Math.abs(value) < 0.01 ? 5 : 2 }).format(value);

export function valuesFor(field, options) {
  const values = options[field.source] ?? options.dropdowns?.[field.source];
  return Array.isArray(values) ? values.filter((value) => field.numeric ? typeof value === "number" && Number.isInteger(value) && value >= field.min && value <= field.max : typeof value === "string" && value.trim().length > 0) : [];
}

export function validOptions(options) {
  return options && typeof options.numeric_ranges === "object" && options.numeric_ranges !== null &&
    FIELDS.filter((field) => field.source).every((field) => valuesFor(field, options).length > 0);
}

export function buildForm(container, options) {
  container.replaceChildren();
  for (const group of GROUPS) {
    const fieldset = document.createElement("fieldset"); fieldset.className = "field-group";
    const legend = document.createElement("legend");
    const icon = document.createElement("span"); icon.className = "group-icon"; icon.ariaHidden = "true"; icon.textContent = group.icon;
    legend.append(icon, document.createTextNode(group.title)); fieldset.append(legend);
    const grid = document.createElement("div"); grid.className = "fields-grid";
    for (const field of group.fields) {
      const wrapper = document.createElement("div"); wrapper.className = `field${field.type === "checkbox" ? " checkbox-field" : ""}`;
      const label = document.createElement("label"); label.htmlFor = field.key;
      label.append(document.createTextNode(field.label));
      const mark = document.createElement("span"); mark.className = field.required ? "required-mark" : "optional-mark"; mark.textContent = field.required ? " *" : " необов’язково"; label.append(mark);
      const control = document.createElement(field.source ? "select" : "input"); control.id = field.key; control.name = field.key; control.required = Boolean(field.required);
      if (field.source) {
        control.append(new Option(field.required ? "Оберіть значення" : "Не вказано", ""));
        for (const value of valuesFor(field, options)) control.append(new Option(String(value), String(value)));
      } else {
        control.type = field.type;
        if (field.type === "number") {
          control.min = field.min; control.max = field.max; control.step = field.integer ? "1" : "any";
          control.placeholder = field.placeholder; control.inputMode = field.integer ? "numeric" : "decimal";
        }
      }
      const descriptions = [];
      if (field.type === "checkbox") { label.prepend(control); wrapper.append(label); } else wrapper.append(label, control);
      const hintParts = [];
      if (field.type === "number") hintParts.push(`Допустимо: ${number(field.min)}–${number(field.max)}.`);
      if (field.hint) hintParts.push(field.hint);
      const range = options.numeric_ranges?.[field.key];
      if (range && Number.isFinite(range.min) && Number.isFinite(range.max)) hintParts.push(`У навчальних даних: ${number(range.min)}–${number(range.max)}. Це не межі валідації.`);
      if (hintParts.length) {
        const hint = document.createElement("p"); hint.id = `${field.key}-hint`; hint.className = "field-hint"; hint.textContent = hintParts.join(" "); wrapper.append(hint); descriptions.push(hint.id);
      }
      const error = document.createElement("p"); error.id = `${field.key}-error`; error.className = "field-error"; error.hidden = true; wrapper.append(error); descriptions.push(error.id);
      control.setAttribute("aria-describedby", descriptions.join(" ")); grid.append(wrapper);
    }
    fieldset.append(grid); container.append(fieldset);
  }
}

export function clearFieldErrors(form) {
  for (const control of form.querySelectorAll("[aria-invalid]")) control.removeAttribute("aria-invalid");
  for (const element of form.querySelectorAll(".field-error")) { element.textContent = ""; element.hidden = true; }
  const summary = form.querySelector("#validation-summary"); summary.hidden = true; summary.textContent = "";
}

export function setFieldError(form, key, message) {
  const field = FIELDS.find((item) => item.key === key);
  if (!field) return false;
  const control = form.elements.namedItem(key);
  const error = document.getElementById(`${key}-error`);
  control.setAttribute("aria-invalid", "true"); error.textContent = message; error.hidden = false;
  return true;
}

export function collectInput(form, options) {
  const payload = {}; const errors = [];
  for (const field of FIELDS) {
    const control = form.elements.namedItem(field.key);
    if (field.type === "checkbox") { payload[field.key] = control.checked; continue; }
    const raw = control.value.trim();
    if (!raw) {
      if (field.required) errors.push({ key: field.key, message: control.validity.badInput ? "Введіть коректне число." : "Заповніть це поле." });
      continue;
    }
    if (field.type === "number" || field.numeric) {
      const value = Number(raw);
      if (!Number.isFinite(value) || value < field.min || value > field.max || ((field.integer || field.numeric) && !Number.isInteger(value))) errors.push({ key: field.key, message: `Вкажіть ${field.integer || field.numeric ? "ціле число" : "число"} від ${number(field.min)} до ${number(field.max)}.` });
      else payload[field.key] = value;
    } else payload[field.key] = raw;
    if (field.source && !valuesFor(field, options).some((value) => String(value) === raw)) errors.push({ key: field.key, message: "Оберіть значення з доступного списку." });
  }
  if (payload.screen_height > payload.screen_width) errors.push({ key: "screen_height", message: "Висота екрана не може бути більшою за ширину." });
  return { payload, errors };
}

export function validSavedInput(input) {
  if (!input || typeof input !== "object" || Array.isArray(input) || Object.keys(input).some((key) => !FIELDS.some((field) => field.key === key))) return false;
  return FIELDS.every((field) => {
    const value = input[field.key];
    if (value == null) return !field.required;
    if (field.type === "checkbox") return typeof value === "boolean";
    if (field.type === "number" || field.numeric) return typeof value === "number" && Number.isFinite(value) && value >= field.min && value <= field.max && (!(field.integer || field.numeric) || Number.isInteger(value));
    return typeof value === "string" && value.trim().length > 0 && value.length < 500;
  }) && (input.screen_height == null || input.screen_height <= input.screen_width);
}
