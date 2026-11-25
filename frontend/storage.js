import { validPrediction } from "./api.js";
import { validSavedInput } from "./form.js";

export function saveLatest(snapshot) {
  try { sessionStorage.setItem(window.APP_CONFIG.storageKeys.latest, JSON.stringify({ version: 1, ...snapshot })); return true; }
  catch { return false; }
}

export function readLatest() {
  try {
    const value = JSON.parse(sessionStorage.getItem(window.APP_CONFIG.storageKeys.latest));
    if (!value || value.version !== 1 || !validPrediction(value.result) || !validSavedInput(value.input)
      || typeof value.createdAt !== "string" || !Number.isFinite(Date.parse(value.createdAt))
      || typeof value.durationMs !== "number" || !Number.isFinite(value.durationMs) || value.durationMs < 0) return null;
    return value;
  } catch { return null; }
}
