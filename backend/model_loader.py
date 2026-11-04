import json
import os
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from backend.schemas import LaptopInput, PredictionOut
from common.logger import get_logger

logger = get_logger("backend.model_loader")


REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = Path(os.getenv("MODEL_DIR", REPO_ROOT / "ml" / "models"))
MODEL_FILE = "best_model.joblib"
METRICS_FILE = "metrics.json"
OPTIONS_FILE = "options.json"

PAIR_SEPARATOR = " | "

DERIVED_FEATURES = {"cpu_brand", "gpu_brand", "cpu_gpu_pair"}
SERVED_FEATURES = set(LaptopInput.model_fields) | DERIVED_FEATURES

PRICE_ROUNDING = -2


class InvalidInputError(ValueError):
    """Вхід пройшов перевірку Pydantic, але суперечить довідникам моделі.

    main.py перетворює цей виняток на HTTP 422 зі списком `errors`.
    """

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class ModelService:
    """Тримає модель і довідники в пам'яті та обслуговує запити на прогноз."""

    def __init__(self, model, metrics: dict, options: dict):
        self.model = model
        self.metrics = metrics
        self.options = options

        self.model_name: str = metrics.get("best_model_name", "unknown")
        # Список і порядок ознак беремо з metrics.json, який train.py зберіг РАЗОМ
        # з моделлю: ознаки й модель не можуть розійтись.
        self.feature_columns: list[str] = list(metrics["feature_columns"])

        # Довідники з options.json (їх готує export_options.py без перенавчання).
        self.dropdowns: dict = options["dropdowns"]
        self.cpu_brand_of: dict[str, str] = options["cpu_brands"]   # модель CPU -> бренд
        self.gpu_brand_of: dict[str, str] = options["gpu_brands"]   # модель GPU -> бренд
        self.numeric_ranges: dict = options["numeric_ranges"]       # діапазони навчання
        self.known_pairs: set[str] = set(self.dropdowns.get("cpu_gpu_pair", []))

        # Fail fast: усі ознаки моделі мають бути забезпечені build_input.
        unsupported = set(self.feature_columns) - SERVED_FEATURES
        if unsupported:
            msg = f"Model needs features that the API cannot build: {sorted(unsupported)}"
            logger.error(msg)
            raise RuntimeError(msg)

        self._init_interval()
        logger.info(
            f"ModelService ready: model={self.model_name}, "
            f"{len(self.feature_columns)} features, {len(self.cpu_brand_of)} CPU models, "
            f"{len(self.gpu_brand_of)} GPU models, interval source={self.interval_source}."
        )


    @classmethod
    def load(cls, models_dir: Path = MODELS_DIR) -> "ModelService":
        """Читає три файли з диска й створює сервіс. Викликається раз, при старті."""
        logger.info(f"Loading artifacts from {models_dir} (scikit-learn {sklearn.__version__}).")
        try:
            # joblib.load «розпаковує» pickle, а він чутливий до версії scikit-learn.
            # Перехоплюємо попередження (напр. InconsistentVersionWarning) і пишемо їх
            # у лог: так розбіжність версій у Docker помітна, а не губиться в консолі.
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                model = joblib.load(models_dir / MODEL_FILE)
            # Одна розбіжність версій дає десятки однакових попереджень (по одному на
            # кожен об'єкт пайплайна), тому групуємо за типом і пишемо по одному рядку.
            by_category: dict[str, list] = {}
            for w in caught:
                by_category.setdefault(w.category.__name__, []).append(w)
            for category, items in by_category.items():
                first_line = str(items[0].message).splitlines()[0]
                logger.warning(
                    f"While loading the model: {len(items)}x {category}, e.g. {first_line}"
                )

            metrics = json.loads((models_dir / METRICS_FILE).read_text(encoding="utf-8"))
            options = json.loads((models_dir / OPTIONS_FILE).read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            logger.error(f"Artifact not found: {exc}. Run ml/train.py and ml/export_options.py first.")
            raise
        except Exception as exc:
            logger.error(f"Failed to load artifacts from {models_dir}: {exc}")
            raise
        return cls(model, metrics, options)

    def _init_interval(self) -> None:
        """Готує множники для діапазону «від-до» навколо прогнозу.

        емпіричні квантилі відношення actual/predicted (ключ
        `error_ratio_quantiles` в options.json, рахується на out-of-fold прогнозах).
        Запасний варіант, якщо їх ще немає: ±MAPE із тестової вибірки. Це груба
        оцінка (при нормальному розподілі помилок вона покриває лише ~57% випадків),
        тому в лог іде попередження.
        """
        quantiles = self.options.get("error_ratio_quantiles")
        if quantiles:
            self.ratio_low = float(quantiles["q10"])
            self.ratio_high = float(quantiles["q90"])
            self.interval_source = "quantiles"
        else:
            mape = float(self.metrics["test_metrics"]["mape"])
            self.ratio_low, self.ratio_high = 1 - mape, 1 + mape
            self.interval_source = "mape_fallback"
            logger.warning(
                "options.json has no 'error_ratio_quantiles': the price range falls back "
                f"to +/-{mape:.1%} (test MAPE). Add quantiles in export_options.py."
            )


    def check_options(self, p: LaptopInput) -> list[str]:
        """Перевіряє вхід за довідниками навчальних даних.

        Кидає InvalidInputError, якщо категорія невідома (жорстка помилка), і
        повертає список попереджень, якщо прогноз можливий, але менш надійний.
        """
        errors: list[str] = []

        # Жорсткі помилки: значення має бути зі списків, які бачить користувач.
        # Для cpu/gpu це ще й технічна необхідність: бренд беремо за моделлю.
        for field in ("company", "type_name", "opsys", "storage_type"):
            value = getattr(p, field)
            if value not in self.dropdowns[field]:
                errors.append(f"{field}: невідоме значення '{value}'")
        if p.cpu_model not in self.cpu_brand_of:
            errors.append(f"cpu_model: невідома модель '{p.cpu_model}'")
        if p.gpu_model not in self.gpu_brand_of:
            errors.append(f"gpu_model: невідома модель '{p.gpu_model}'")

        if errors:
            logger.warning(f"Rejected input: {errors}")
            raise InvalidInputError(errors)

        # М'які попередження: дерева не екстраполюють, поза діапазоном навчання
        # модель віддасть «найближче відоме» значення, яке виглядає правдоподібно.
        warns: list[str] = []
        if p.ram_gb not in self.dropdowns["ram_gb"]:
            warns.append(f"ram_gb={p.ram_gb}: такого обсягу не було в навчальних даних")
        for field, rng in self.numeric_ranges.items():
            value = getattr(p, field)
            if not rng["min"] <= value <= rng["max"]:
                warns.append(
                    f"{field}={value} поза діапазоном навчальних даних "
                    f"[{rng['min']:.4g}; {rng['max']:.4g}]"
                )
        pair = f"{p.cpu_model}{PAIR_SEPARATOR}{p.gpu_model}"
        if pair not in self.known_pairs:
            warns.append("Така комбінація CPU і GPU не зустрічалась у навчальних даних")

        if warns:
            logger.info(f"Input accepted with warnings: {warns}")
        return warns


    def build_input(self, p: LaptopInput) -> pd.DataFrame:
        """Перетворює вхід форми на DataFrame у форматі навчальних даних.

        Модель — це Pipeline із ColumnTransformer, який вибирає колонки ЗА НАЗВОЮ,
        тому назви, типи й одиниці мають збігатися з навчальними (training-serving
        skew — головне джерело тихих помилок).
        """
        row = p.model_dump()                                   # поля форми -> dict
        row["cpu_brand"] = self.cpu_brand_of[p.cpu_model]      # похідні ознаки: бренд за моделлю
        row["gpu_brand"] = self.gpu_brand_of[p.gpu_model]
        row["cpu_gpu_pair"] = f"{p.cpu_model}{PAIR_SEPARATOR}{p.gpu_model}"
        row["is_ips"] = int(p.is_ips)                          # у навчанні булеві були 0/1
        row["is_touchscreen"] = int(p.is_touchscreen)

        # Вибірка за feature_columns задає порядок колонок і відкидає зайве
        # (напр. screen_height). Якщо колонки бракує, буде KeyError: краще впасти
        # голосно, ніж прогнозувати без ознаки.
        try:
            return pd.DataFrame([row])[self.feature_columns]
        except KeyError as exc:
            logger.error(f"Feature mismatch while building the model input: {exc}")
            raise

    def predict(self, X: pd.DataFrame) -> float:
        """Прогноз для одного рядка. Ціна вже у вихідній шкалі: TransformedTargetRegressor
        сам застосовує expm1, тому додаткових перетворень не потрібно."""
        price = float(self.model.predict(X)[0])
        if not np.isfinite(price) or price <= 0:
            logger.error(f"Model returned an invalid price: {price}")
            raise RuntimeError("Model returned an invalid prediction")
        return price

    def interval(self, price: float) -> tuple[float, float]:
        """Типовий діапазон: множники ratio_low/ratio_high з _init_interval."""
        return price * self.ratio_low, price * self.ratio_high

    def predict_laptop(self, p: LaptopInput) -> PredictionOut:
        """Повний цикл для одного запиту: перевірка -> вхід -> прогноз -> діапазон."""
        warns = self.check_options(p)
        X = self.build_input(p)
        price = self.predict(X)
        low, high = self.interval(price)
        logger.info(f"Prediction: {price:.0f} (range {low:.0f}..{high:.0f}) for {p.company} {p.type_name}")
        return PredictionOut(
            predicted_price=round(price, PRICE_ROUNDING),
            price_low=round(low, PRICE_ROUNDING),
            price_high=round(high, PRICE_ROUNDING),
            model_name=self.model_name,
            warnings=warns,
        )


    def options_payload(self) -> dict:
        """Довідники для побудови форми. Список пар CPU+GPU (249 рядків) фронтенду не потрібен."""
        return {
            "dropdowns": {k: v for k, v in self.dropdowns.items() if k != "cpu_gpu_pair"},
            "cpu_models": sorted(self.cpu_brand_of),
            "gpu_models": sorted(self.gpu_brand_of),
            "numeric_ranges": self.numeric_ranges,
        }

    def model_info(self) -> dict:
        """Зведення метрик для сторінки «Аналітика»."""
        cv_summary = {}
        for name, result in self.metrics.get("cv_results", {}).items():
            # Ключі в metrics.json можуть бути в різному регістрі (validation_RMSE / validation_rmse)
            result = {k.lower(): np.asarray(v, dtype=float) for k, v in result.items()}
            cv_summary[name] = {
                "cv_rmse_mean": float(result["validation_rmse"].mean()),
                "cv_rmse_std": float(result["validation_rmse"].std(ddof=1)),
                "cv_r2_mean": float(result["validation_r2"].mean()),
            }
        return {
            "best_model_name": self.model_name,
            "test_metrics": self.metrics.get("test_metrics", {}),
            "cv_results": cv_summary,
            "tuning": self.metrics.get("tuning", {}),
            "interval_source": self.interval_source,
            "n_features": len(self.feature_columns),
        }
    