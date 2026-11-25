"""Run inside server_backend: docker exec -i server_backend python - < this_file."""

import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from backend.db_con import get_connection

BASE_URL = "http://127.0.0.1:" + os.environ.get("UVICORN_PORT", "8000")
PAYLOAD = {
    "company": "Lenovo", "type_name": "Notebook", "inches": 15.6,
    "screen_width": 1920, "screen_height": 1080, "is_ips": True,
    "is_touchscreen": False, "cpu_model": "Core i5 7200U", "cpu_ghz": 2.5,
    "ram_gb": 8, "storage_type": "SSD", "storage_gb": 256,
    "gpu_model": "HD Graphics 620", "opsys": "Windows 10", "weight": 2.0,
}


def request(path, payload=None, expected_status=200):
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE_URL + path, data=body,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        assert response.code == expected_status, (path, response.code, response.read())
        raw = response.read()
        return json.loads(raw) if raw else None


def prediction_count():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM model_predictions")
            count = cur.fetchone()[0]
    conn.close()
    return count


def main():
    assert sys.version_info[:3] == (3, 12, 6), sys.version
    assert importlib.util.find_spec("etl") is None
    assert importlib.util.find_spec("polars") is None
    health = request("/health")
    assert health == {"status": "ok", "model_loaded": True, "db_ok": True}, health
    assert "No OS" in request("/api/options")["dropdowns"]["opsys"]
    assert request("/api/model-info")["interval_source"] == "quantiles"
    assert "/api/predict" in request("/openapi.json")["paths"]
    for path in ("/docs", "/static/img/feature_importance.png"):
        with urllib.request.urlopen(BASE_URL + path, timeout=15) as response:
            assert response.status == 200

    before = prediction_count()
    normal = request("/api/predict", PAYLOAD)
    assert 0 < normal["price_low"] < normal["predicted_price"] < normal["price_high"]
    missing = request("/api/predict", {k: v for k, v in PAYLOAD.items() if k != "opsys"})
    assert len([w for w in missing["warnings"] if w.startswith("Не вказано: opsys.")]) == 1
    no_os = request("/api/predict", {**PAYLOAD, "opsys": "No Os"})
    unknown = request("/api/predict", {**PAYLOAD, "opsys": "Unknown"})
    assert no_os["predicted_price"] == unknown["predicted_price"]
    error = request("/api/predict", {**PAYLOAD, "company": "Nokia"}, expected_status=422)
    assert error["detail"][0]["loc"] == ["body", "company"]
    request("/api/predict", {**PAYLOAD, "weight": 0.1}, expected_status=422)
    request("/api/predict", {**PAYLOAD, "unexpected": True}, expected_status=422)

    deadline = time.monotonic() + 10
    while prediction_count() < before + 4 and time.monotonic() < deadline:
        time.sleep(0.1)
    assert prediction_count() == before + 4
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='laptops_clean'"
            )
            clean_schema = dict(cur.fetchall())
            assert clean_schema["opsys"] == "character varying"
            assert clean_schema["cpu_gpu_pair"] == "text"
            assert clean_schema["storage_gb"] == "double precision"
            cur.execute(
                "SELECT input_json, pridicted_price, pg_typeof(pridicted_price)::text, "
                "jsonb_typeof(pridicted_price) FROM model_predictions "
                "ORDER BY predict_id DESC LIMIT 1"
            )
            saved_input, saved_price, sql_type, json_type = cur.fetchone()
            assert saved_input["opsys"] == "Unknown"
            assert saved_price == unknown["predicted_price"]
            assert (sql_type, json_type) == ("jsonb", "number")

            # Validate new DDL using rollback; no seed, ETL, or training.
            cur.execute(
                "INSERT INTO raw_laptops(company, opsys, price) "
                "VALUES (%s, %s, %s) RETURNING raw_laps_id",
                ("smoke", "No OS", 100),
            )
            raw_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO laptops_clean(raw_id, inches, cpu_ghz, storage_gb, "
                "weight, opsys, cpu_gpu_pair, price) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING opsys, cpu_gpu_pair, storage_gb",
                (raw_id, 15.6, 2.5, 256.0, 2.0, "No OS", "CPU | GPU", 100),
            )
            assert cur.fetchone() == ("No OS", "CPU | GPU", 256.0)
    finally:
        conn.rollback()
        conn.close()

    print(json.dumps({
        "health": health, "prediction": normal["predicted_price"],
        "missing_opsys_warning_count": 1, "saved_jsonb_predictions": 4,
        "no_os_legacy_parity": True, "backend_without_etl_polars": True,
        "ddl_roundtrip": True, "validation_422": True,
    }))


if __name__ == "__main__":
    main()
