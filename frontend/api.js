/* HTTP-шар: жодних демонстраційних відповідей або підміни прогнозу. */
export class ApiError extends Error {
  constructor(message, { status = null, kind = "network", issues = [], code = null } = {}) {
    super(message);
    Object.assign(this, { status, kind, issues, code });
  }
}

export async function requestJSON(url, { method = "GET", body, timeoutMs = window.APP_CONFIG.requestTimeoutMs } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(url, {
      method, signal: controller.signal, headers: { Accept: "application/json", ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    let data;
    try { data = await response.json(); }
    catch (error) {
      if (controller.signal.aborted) throw error;
      throw new ApiError("Сервер повернув відповідь у неочікуваному форматі. Спробуйте ще раз.", { status: response.status, kind: "format" });
    }
    if (!response.ok) {
      // Не показуємо сирі 5xx-відповіді, HTML або діагностику сервера.
      const issues = response.status === 422 && Array.isArray(data?.detail)
        ? data.detail.filter((issue) => Array.isArray(issue.loc) && typeof issue.msg === "string")
          .slice(0, 30).map(({ loc, msg, type }) => ({ loc, msg: msg.slice(0, 400), type: typeof type === "string" ? type.slice(0, 80) : "" })) : [];
      const code = typeof data?.code === "string" && /^[a-zA-Z0-9_.-]{1,80}$/.test(data.code) ? data.code : null;
      throw new ApiError(response.status === 422 ? "Перевірте характеристики ноутбука." : response.status >= 500 ? "Сервер не зміг виконати запит. Спробуйте пізніше." : "Запит не виконано. Перевірте дані та спробуйте ще раз.", { status: response.status, kind: "http", issues, code });
    }
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) throw new ApiError("Час очікування вичерпано. Спробуйте ще раз.", { status: response?.status ?? null, kind: "timeout" });
    throw new ApiError("Не вдалося отримати відповідь. Перевірте з’єднання та спробуйте ще раз.", { status: response?.status ?? null, kind: "network" });
  } finally { clearTimeout(timeout); }
}

export function validPrediction(data) {
  return data && ["predicted_price", "price_low", "price_high"].every((key) => typeof data[key] === "number" && Number.isFinite(data[key]) && data[key] >= 0)
    && data.price_low <= data.predicted_price && data.predicted_price <= data.price_high
    && typeof data.model_name === "string" && data.model_name.length > 0 && data.model_name.length < 200
    && Array.isArray(data.warnings) && data.warnings.every((item) => typeof item === "string" && item.length < 2000);
}
