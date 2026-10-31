"""
ml/evaluate.py — оцінювання навченої моделі.

Запуск з кореня проєкту:
    python -m ml.evaluate
    python -m ml.evaluate --skip-importance          # без завантаження .joblib
    python -m ml.evaluate --models-dir ml/models_smoke

Читає артефакти, створені ml/train.py (metrics.json, test_predictions.parquet,
best_model.joblib), рахує підсумкові показники та будує графіки для
пояснювальної записки й сторінки analytics.html.

Модель тут НЕ перенавчається, а тестова вибірка використовується лише для
опису якості, а не для вибору чи налаштування моделі.
"""

import argparse
import json
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")  # без GUI: працює і в терміналі, і в Docker
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
)


from common.logger import get_logger


RANDOM_STATE = 67
PRICE_UNIT = " грн"          
MIN_SEGMENT_SIZE = 10  
TOP_N_FEATURES = 15

ML_DIR = Path(__file__).resolve().parent
REPO_ROOT = ML_DIR.parent
DEFAULT_MODELS_DIR = ML_DIR / "models"
DEFAULT_FIGURE_DIRS = [
    REPO_ROOT / "docs" / "evaluation",
    REPO_ROOT / "frontend" / "img",
]

MODEL_LABELS = {
    "Dummy": "Dummy\n(середнє)",
    "LinearRegression": "Лінійна\nрегресія",
    "RandomForest": "Random\nForest",
    "HistGradientBoosting": "Hist\nGradientBoosting",
}
FEATURE_LABELS = {
    "company": "Бренд",
    "type_name": "Тип ноутбука",
    "inches": "Діагональ",
    "screen_width": "Ширина екрана",
    "is_ips": "IPS",
    "is_touchscreen": "Сенсорний екран",
    "cpu_brand": "Бренд CPU",
    "cpu_model": "Модель CPU",
    "cpu_ghz": "Частота CPU",
    "ram_gb": "RAM",
    "storage_type": "Тип накопичувача",
    "storage_gb": "Обсяг накопичувача",
    "gpu_brand": "Бренд GPU",
    "gpu_model": "Модель GPU",
    "opsys": "ОС",
    "weight": "Вага",
    "cpu_gpu_pair": "Комбінація моделей CPU та GPU"
}

logger = get_logger("ml.evaluate")
sns.set_theme(style="whitegrid")


# ----------------------------------------------------------------------------
# Допоміжні функції
# ----------------------------------------------------------------------------
def price_label(text: str = "Ціна") -> str:
    return f"{text}{PRICE_UNIT}"


def format_money_axis(ax, axis: str = "both") -> None:
    """Розділяє розряди пробілом: 12 345 замість 12345."""
    formatter = mticker.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", " "))
    if axis in ("x", "both"):
        ax.xaxis.set_major_formatter(formatter)
    if axis in ("y", "both"):
        ax.yaxis.set_major_formatter(formatter)


def save_fig(fig, name: str, figure_dirs: list) -> None:
    for directory in figure_dirs:
        directory.mkdir(parents=True, exist_ok=True)
        fig.savefig(directory / f"{name}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Figure saved: {name}.png -> {', '.join(str(d) for d in figure_dirs)}")


def load_artifacts(models_dir: Path):
    """Читає metrics.json і test_predictions.parquet, додає колонку залишків."""
    logger.info(f"Loading artifacts from {models_dir}.")
    with open(models_dir / "metrics.json", encoding="utf-8") as fh:
        metrics = json.load(fh)

    predictions = pd.read_parquet(models_dir / "test_predictions.parquet")
    missing = {"actual_price", "predicted_price"} - set(predictions.columns)
    if missing:
        raise ValueError(f"test_predictions.parquet has no columns: {sorted(missing)}")

    predictions["residual"] = predictions["actual_price"] - predictions["predicted_price"]
    logger.info(f"Loaded {len(predictions)} test rows and metrics for "
                f"{len(metrics.get('cv_results', {}))} models.")
    return metrics, predictions


# ----------------------------------------------------------------------------
# Числові підсумки
# ----------------------------------------------------------------------------
def bootstrap_ci(pred: pd.DataFrame, n_boot: int = 2000, alpha: float = 0.05) -> dict:
    """95% довірчі інтервали метрик на тесті (бутстреп по рядках).

    Тестова вибірка невелика, тому одне число RMSE/R² має помітну випадкову
    похибку: інтервал показує, наскільки цьому числу можна довіряти."""
    rng = np.random.default_rng(RANDOM_STATE)
    y = pred["actual_price"].to_numpy()
    p = pred["predicted_price"].to_numpy()
    n = len(y)
    samples = {"rmse": [], "mae": [], "r2": [], "mape_percent": []}
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        yy, err = y[idx], y[idx] - p[idx]
        samples["rmse"].append(np.sqrt(np.mean(err ** 2)))
        samples["mae"].append(np.mean(np.abs(err)))
        samples["r2"].append(1 - np.sum(err ** 2) / np.sum((yy - yy.mean()) ** 2))
        samples["mape_percent"].append(np.mean(np.abs(err) / yy) * 100)
    low, high = 100 * alpha / 2, 100 * (1 - alpha / 2)
    return {k: [float(np.percentile(v, low)), float(np.percentile(v, high))]
            for k, v in samples.items()}


def compute_summary(pred: pd.DataFrame, metrics: dict) -> dict:
    """Метрики на тесті, перераховані з нуля, + порівняння з крос-валідацією."""
    y = pred["actual_price"]
    p = pred["predicted_price"]
    residual = pred["residual"]
    relative_error = residual.abs() / y

    summary = {
        "n_test": int(len(pred)),
        "rmse": float(np.sqrt(mean_squared_error(y, p))),
        "mae": float(mean_absolute_error(y, p)),
        "r2": float(r2_score(y, p)),
        "mape_percent": float(mean_absolute_percentage_error(y, p) * 100),
        "median_abs_error": float(residual.abs().median()),
        "mean_error_bias": float(residual.mean()),   # >0: модель у середньому занижує ціну
        "mean_price": float(y.mean()),
        "share_within_10_percent": float((relative_error <= 0.10).mean() * 100),
        "share_within_20_percent": float((relative_error <= 0.20).mean() * 100),
    }
    summary["mae_percent_of_mean_price"] = summary["mae"] / summary["mean_price"] * 100

    saved = metrics.get("test_metrics", {})
    if "rmse" in saved and not np.isclose(saved["rmse"], summary["rmse"], rtol=1e-6):
        logger.warning(
            f"RMSE from metrics.json ({saved['rmse']:.2f}) differs from recomputed "
            f"({summary['rmse']:.2f}): перевірте, що файли з одного запуску train.py."
        )

    best_name = metrics.get("best_model_name")
    tuned = metrics.get("tuning", {}).get(best_name)
    if tuned:
        summary["best_model_name"] = best_name
        summary["cv_rmse_tuned"] = float(tuned["cv_rmse"])
        summary["test_to_cv_rmse_ratio"] = summary["rmse"] / float(tuned["cv_rmse"])
    return summary


def cv_table(metrics: dict) -> pd.DataFrame:
    """Зведена таблиця крос-валідації (до тюнінгу) для всіх моделей."""
    rows = []
    for name, result in metrics.get("cv_results", {}).items():
        result = {k.lower(): np.asarray(v, dtype=float) for k, v in result.items()}
        rows.append({
            "model": name,
            "cv_rmse_mean": result["validation_rmse"].mean(),
            "cv_rmse_std": result["validation_rmse"].std(ddof=1),
            "train_rmse_mean": result["train_rmse"].mean(),
            "cv_mae_mean": result["validation_mae"].mean(),
            "cv_r2_mean": result["validation_r2"].mean(),
            "cv_r2_median": np.median(result["validation_r2"]),
        })
        tuned = metrics.get("tuning", {}).get(name)
        rows[-1]["cv_rmse_tuned"] = float(tuned["cv_rmse"]) if tuned else np.nan
    return pd.DataFrame(rows)


def segment_errors(pred: pd.DataFrame) -> pd.DataFrame:
    """Похибка за сегментами: тип ноутбука, цінова група, бренд."""
    df = pred.copy()
    df["abs_error"] = df["residual"].abs()
    df["pct_error"] = df["abs_error"] / df["actual_price"] * 100
    df["price_group"] = pd.qcut(
        df["actual_price"], 4,
        labels=["Q1 (найдешевші)", "Q2", "Q3", "Q4 (найдорожчі)"],
    ).astype(str)

    groupings = {"price_group": "Цінова група"}
    if "type_name" in df.columns:
        groupings["type_name"] = "Тип ноутбука"
    if "company" in df.columns:
        counts = df["company"].map(df["company"].value_counts())
        df["company_group"] = df["company"].where(counts >= MIN_SEGMENT_SIZE, "Інші")
        groupings["company_group"] = "Бренд"

    rows = []
    for column, title in groupings.items():
        grouped = df.groupby(column, observed=True).agg(
            n=("abs_error", "size"),
            mae=("abs_error", "mean"),
            mape_percent=("pct_error", "mean"),
            bias=("residual", "mean"),
        )
        for segment, record in grouped.iterrows():
            rows.append({"grouping": title, "segment": segment, **record.to_dict()})
    return pd.DataFrame(rows)


def compute_importance(model_path: Path, pred: pd.DataFrame, feature_columns: list):
    """Permutation importance на сирих колонках (до one-hot): зручно для інтерпретації."""
    logger.info("Loading model for permutation importance.")
    model = joblib.load(model_path)
    X = pred[feature_columns]
    y = pred["actual_price"].to_numpy()

    reproduced = model.predict(X)
    max_diff = float(np.abs(reproduced - pred["predicted_price"].to_numpy()).max())
    if max_diff > 1e-3:
        logger.warning(
            f"Model predictions differ from saved ones by up to {max_diff:.4f}: "
            "імовірно інша версія scikit-learn або інший набір колонок."
        )
    else:
        logger.info(f"Model reproduces saved predictions (max diff {max_diff:.2e}).")

    result = permutation_importance(
        model, X, y,
        scoring="neg_root_mean_squared_error",
        n_repeats=20,
        random_state=RANDOM_STATE,
        n_jobs=1,
    )
    importance = pd.DataFrame({
        "feature": feature_columns,
        "importance_mean": result.importances_mean,
        "importance_std": result.importances_std,
    }).sort_values("importance_mean", ascending=False)
    return importance, max_diff


# ----------------------------------------------------------------------------
# Графіки
# ----------------------------------------------------------------------------
def plot_pred_vs_actual(pred: pd.DataFrame, summary: dict, figure_dirs: list) -> None:
    y, p = pred["actual_price"], pred["predicted_price"]
    limit = [0, max(y.max(), p.max()) * 1.05]

    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    ax.scatter(y, p, alpha=0.6, s=28, edgecolor="none")
    ax.plot(limit, limit, "--", color="crimson", label="Ідеальний прогноз")
    ax.set(xlim=limit, ylim=limit,
           xlabel=price_label("Фактична ціна"), ylabel=price_label("Прогнозована ціна"),
           title="Прогноз проти фактичної ціни (тестова вибірка)")
    ax.text(0.04, 0.96,
            f"R² = {summary['r2']:.3f}\nRMSE = {summary['rmse']:,.0f}\nMAE = {summary['mae']:,.0f}"
            .replace(",", " "),
            transform=ax.transAxes, va="top",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.85))
    ax.legend(loc="lower right")
    format_money_axis(ax)
    save_fig(fig, "pred_vs_actual", figure_dirs)


def plot_residuals(pred: pd.DataFrame, summary: dict, figure_dirs: list) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    sns.histplot(pred["residual"], bins=30, kde=True, ax=axes[0])
    axes[0].axvline(0, color="crimson", ls="--")
    axes[0].axvline(summary["mean_error_bias"], color="darkorange", ls=":",
                    label=f"Середнє = {summary['mean_error_bias']:,.0f}".replace(",", " "))
    axes[0].set(title="Розподіл залишків (факт − прогноз)", xlabel=price_label("Залишок"),
                ylabel="Кількість")
    axes[0].legend()

    axes[1].scatter(pred["predicted_price"], pred["residual"], alpha=0.6, s=25, edgecolor="none")
    axes[1].axhline(0, color="crimson", ls="--")
    axes[1].set(title="Залишки залежно від прогнозу",
                xlabel=price_label("Прогнозована ціна"), ylabel=price_label("Залишок"))
    format_money_axis(axes[1])
    fig.tight_layout()
    save_fig(fig, "residuals", figure_dirs)


def plot_model_comparison(cv: pd.DataFrame, summary: dict, figure_dirs: list) -> None:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = np.arange(len(cv))
    ax.bar(x, cv["cv_rmse_mean"], yerr=cv["cv_rmse_std"], capsize=5, color="#8fb4d9",
           label="CV до тюнінгу (середнє ± σ)")

    tuned = cv["cv_rmse_tuned"].notna()
    ax.scatter(x[tuned], cv.loc[tuned, "cv_rmse_tuned"], marker="D", s=80,
               color="darkorange", zorder=5, label="CV після тюнінгу")
    best = summary.get("best_model_name", "найкраща модель")
    ax.axhline(summary["rmse"], ls="--", color="crimson",
               label=f"Тест, {best}: RMSE = {summary['rmse']:,.0f}".replace(",", " "))

    ax.set_xticks(x)
    ax.set_xticklabels([MODEL_LABELS.get(m, m) for m in cv["model"]])
    ax.set(ylabel="RMSE", title="Порівняння моделей за RMSE (менше — краще)")
    ax.grid(axis="x", visible=False)
    format_money_axis(ax, "y")
    ax.legend()
    save_fig(fig, "model_comparison", figure_dirs)


def plot_overfitting(cv: pd.DataFrame, figure_dirs: list) -> None:
    data = cv[cv["model"] != "Dummy"]
    x = np.arange(len(data))
    width = 0.38

    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.bar(x - width / 2, data["train_rmse_mean"], width, label="Навчання")
    ax.bar(x + width / 2, data["cv_rmse_mean"], width, yerr=data["cv_rmse_std"],
           capsize=4, label="Валідація (CV)")
    ax.set_xticks(x)
    ax.set_xticklabels([MODEL_LABELS.get(m, m) for m in data["model"]])
    ax.set(ylabel="RMSE", title="RMSE на навчанні та на валідації (до тюнінгу)")
    ax.grid(axis="x", visible=False)
    format_money_axis(ax, "y")
    ax.legend()
    save_fig(fig, "train_vs_validation", figure_dirs)


def plot_segments(segments: pd.DataFrame, figure_dirs: list) -> None:
    groupings = list(segments["grouping"].unique())
    fig, axes = plt.subplots(2, len(groupings), figsize=(5.5 * len(groupings), 9), squeeze=False)

    for col, grouping in enumerate(groupings):
        part = segments[segments["grouping"] == grouping]
        labels = [f"{s}\n(n={int(n)})" for s, n in zip(part["segment"], part["n"])]
        axes[0, col].bar(labels, part["mae"], color="#8fb4d9")
        axes[0, col].set(title=f"{grouping}: MAE", ylabel=price_label("MAE"))
        format_money_axis(axes[0, col], "y")
        axes[1, col].bar(labels, part["mape_percent"], color="#e8a87c")
        axes[1, col].set(title=f"{grouping}: MAPE", ylabel="MAPE, %")
        for ax in axes[:, col]:
            ax.grid(axis="x", visible=False)
            ax.tick_params(axis="x", rotation=40, labelsize=8)
            for tick in ax.get_xticklabels():
                tick.set_ha("right")
    fig.suptitle("Похибка моделі за сегментами тестової вибірки", fontsize=14)
    fig.tight_layout()
    save_fig(fig, "segment_errors", figure_dirs)


def plot_importance(importance: pd.DataFrame, figure_dirs: list) -> None:
    top = importance.head(TOP_N_FEATURES).iloc[::-1]
    labels = [FEATURE_LABELS.get(f, f) for f in top["feature"]]

    fig, ax = plt.subplots(figsize=(8, 0.45 * len(top) + 1.8))
    ax.barh(labels, top["importance_mean"], xerr=top["importance_std"], capsize=3, color="#6a9fb5")
    ax.set(xlabel="Зростання RMSE при перемішуванні ознаки",
           title="Важливість ознак (permutation importance, тест)")
    format_money_axis(ax, "x")
    save_fig(fig, "feature_importance", figure_dirs)


# ----------------------------------------------------------------------------
# Точка входу
# ----------------------------------------------------------------------------
def print_report(summary: dict, cv: pd.DataFrame) -> None:
    print("\n=== Підсумок на тестовій вибірці ===")
    print(f"  n = {summary['n_test']}, середня ціна = {summary['mean_price']:,.0f}".replace(",", " "))
    print(f"  RMSE = {summary['rmse']:,.0f} | MAE = {summary['mae']:,.0f} | R² = {summary['r2']:.3f}"
          .replace(",", " "))
    print(f"  MAPE = {summary['mape_percent']:.1f}% | медіанна абс. помилка = "
          f"{summary['median_abs_error']:,.0f}".replace(",", " "))
    print(f"  Зміщення (факт − прогноз) = {summary['mean_error_bias']:,.0f}".replace(",", " "))
    print(f"  Прогноз у межах ±10%: {summary['share_within_10_percent']:.0f}% ; "
          f"±20%: {summary['share_within_20_percent']:.0f}% ноутбуків")
    if "cv_rmse_tuned" in summary:
        print(f"  CV RMSE (тюнінг) = {summary['cv_rmse_tuned']:,.0f}; "
              f"тест/CV = {summary['test_to_cv_rmse_ratio']:.2f}".replace(",", " "))
    print("\n=== Крос-валідація до тюнінгу ===")
    print(cv.round(1).to_string(index=False))


def main(models_dir: Path, figure_dirs: list, skip_importance: bool) -> None:
    logger.info("Starting evaluation workflow.")
    try:
        metrics, pred = load_artifacts(models_dir)
        summary = compute_summary(pred, metrics)
        cv = cv_table(metrics)
        segments = segment_errors(pred)

        plot_pred_vs_actual(pred, summary, figure_dirs)
        plot_residuals(pred, summary, figure_dirs)
        plot_model_comparison(cv, summary, figure_dirs)
        plot_overfitting(cv, figure_dirs)
        plot_segments(segments, figure_dirs)

        importance = None
        model_path = models_dir / "best_model.joblib"
        if skip_importance:
            logger.info("Permutation importance skipped (--skip-importance).")
        elif not model_path.exists():
            logger.warning(f"{model_path} not found: permutation importance skipped.")
        else:
            try:
                importance, max_diff = compute_importance(
                    model_path, pred, metrics["feature_columns"])
                summary["model_reproduces_saved_predictions"] = bool(max_diff <= 1e-3)
                plot_importance(importance, figure_dirs)
            except Exception as exc:  # версія sklearn, відсутні колонки тощо
                logger.warning(f"Permutation importance failed and was skipped: {exc}")

        tables_dir = figure_dirs[0]
        tables_dir.mkdir(parents=True, exist_ok=True)
        cv.to_csv(tables_dir / "cv_comparison.csv", index=False)
        segments.to_csv(tables_dir / "segment_errors.csv", index=False)
        if importance is not None:
            importance.to_csv(tables_dir / "permutation_importance.csv", index=False)
        with open(models_dir / "evaluation_summary.json", "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)

        print_report(summary, cv)
        logger.info("Evaluation workflow completed successfully.")
    except Exception as exc:
        logger.error(f"Evaluation workflow failed: {exc}")
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Оцінювання навченої моделі")
    parser.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR,
                        help="тека з metrics.json, test_predictions.parquet, best_model.joblib")
    parser.add_argument("--out-dir", type=Path, nargs="+", default=None,
                        help="куди зберігати графіки (за замовчуванням docs/evaluation "
                             "і backend/static/img)")
    parser.add_argument("--skip-importance", action="store_true",
                        help="не завантажувати модель і не рахувати permutation importance")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        models_dir=args.models_dir,
        figure_dirs=args.out_dir or DEFAULT_FIGURE_DIRS,
        skip_importance=args.skip_importance,
    )
