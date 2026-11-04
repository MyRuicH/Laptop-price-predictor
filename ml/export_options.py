import json
import numpy as np
import joblib
from decimal import Decimal
from pathlib import Path

from psycopg2.extras import RealDictCursor
from sklearn.model_selection import KFold, cross_val_predict

from etl.db_utils import get_connection
from ml.train import RANDOM_STATE, get_prepared_data, select_features, features_splitting


# Шлях до директорії поточного файлу
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = BASE_DIR / "models" / "options.json"
MODELS_DIR = BASE_DIR / "models" 


def json_decimal_default(value):
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def compute_error_ratio_quantiles() -> dict:
    """Квантилі відношення actual/predicted на out-of-fold прогнозах тренувальної вибірки."""
    best_model = joblib.load(MODELS_DIR / "best_model.joblib")

    df = get_prepared_data()
    X, y = select_features(df=df)
    X_train, _, y_train, _ = features_splitting(X=X, y=y)   # той самий поділ, тест не використовується

    oof = cross_val_predict(
        best_model, X_train, y_train,
        cv=KFold(5, shuffle=True, random_state=RANDOM_STATE),
    )
    ratio = y_train / oof
    return {"q10": float(np.quantile(ratio, 0.10)), "q90": float(np.quantile(ratio, 0.90))}


def export_options():
    conn = get_connection()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:

            # 1. Значення для dropdown-полів
            cursor.execute("""
                SELECT
                    ARRAY_AGG(DISTINCT company ORDER BY company)
                        FILTER (WHERE company IS NOT NULL) AS company,

                    ARRAY_AGG(DISTINCT type_name ORDER BY type_name)
                        FILTER (WHERE type_name IS NOT NULL) AS type_name,

                    ARRAY_AGG(DISTINCT opSys ORDER BY opSys)
                        FILTER (WHERE opSys IS NOT NULL) AS opsys,

                    ARRAY_AGG(DISTINCT storage_type ORDER BY storage_type)
                        FILTER (WHERE storage_type IS NOT NULL) AS storage_type,

                    ARRAY_AGG(DISTINCT ram_gb ORDER BY ram_gb)
                        FILTER (WHERE ram_gb IS NOT NULL) AS ram_gb,

                    ARRAY_AGG(
                        DISTINCT screen_width
                        ORDER BY screen_width
                    ) FILTER (
                        WHERE screen_width IS NOT NULL
                    ) AS screen_width,

                    ARRAY_AGG(
                        DISTINCT screen_height
                        ORDER BY screen_height
                    ) FILTER (
                        WHERE screen_height IS NOT NULL
                    ) AS screen_height,

                    ARRAY_AGG(
                        DISTINCT cpu_gpu_pair
                        ORDER BY cpu_gpu_pair
                    ) FILTER (
                        WHERE cpu_gpu_pair IS NOT NULL
                    ) AS cpu_gpu_pair

                FROM laptops_clean;
            """)

            dropdowns = dict(cursor.fetchone())

            # 2. Мапа cpu_model -> cpu_brand
            cursor.execute("""
                SELECT DISTINCT cpu_model, cpu_brand
                FROM laptops_clean
                WHERE cpu_model IS NOT NULL
                  AND cpu_brand IS NOT NULL
                ORDER BY cpu_model;
            """)

            cpu_brands = {
                row["cpu_model"]: row["cpu_brand"]
                for row in cursor.fetchall()
            }

            # 3. Мапа gpu_model -> gpu_brand
            cursor.execute("""
                SELECT DISTINCT gpu_model, gpu_brand
                FROM laptops_clean
                WHERE gpu_model IS NOT NULL
                  AND gpu_brand IS NOT NULL
                ORDER BY gpu_model;
            """)

            gpu_brands = {
                row["gpu_model"]: row["gpu_brand"]
                for row in cursor.fetchall()
            }

            # 4. Мінімальні та максимальні значення
            cursor.execute("""
                SELECT
                    MIN(inches) AS inches_min,
                    MAX(inches) AS inches_max,

                    MIN(weight) AS weight_min,
                    MAX(weight) AS weight_max,

                    MIN(cpu_ghz) AS cpu_ghz_min,
                    MAX(cpu_ghz) AS cpu_ghz_max,

                    MIN(storage_gb) AS storage_gb_min,
                    MAX(storage_gb) AS storage_gb_max

                FROM laptops_clean;
            """)

            ranges = cursor.fetchone()

            numeric_ranges = {
                "inches": {
                    "min": ranges["inches_min"],
                    "max": ranges["inches_max"]
                },
                "weight": {
                    "min": ranges["weight_min"],
                    "max": ranges["weight_max"]
                },
                "cpu_ghz": {
                    "min": ranges["cpu_ghz_min"],
                    "max": ranges["cpu_ghz_max"]
                },
                "storage_gb": {
                    "min": ranges["storage_gb_min"],
                    "max": ranges["storage_gb_max"]
                }
            }

            # 5. Формування фінального словника
            options = {
                "dropdowns": dropdowns,
                "cpu_brands": cpu_brands,
                "gpu_brands": gpu_brands,
                "numeric_ranges": numeric_ranges,
                "error_ratio_quantiles": compute_error_ratio_quantiles()
            }

            # 6. запис JSON
            with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
                json.dump(
                    options,
                    fh,
                    ensure_ascii=False,
                    indent=4,
                    default=json_decimal_default
                )

            print(f"Options successfully exported to {OUTPUT_PATH}")

    finally:
        conn.close()


if __name__ == "__main__":
    export_options()
