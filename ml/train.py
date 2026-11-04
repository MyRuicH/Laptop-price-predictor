import polars as pl
import numpy as np
import json
from pathlib import Path

import joblib
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.pipeline import Pipeline

from sklearn.model_selection import KFold, cross_validate
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    mean_absolute_percentage_error,
    r2_score,
)

from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import (
    RandomForestRegressor,
    HistGradientBoostingRegressor,
)

from etl.db_utils import load_table_data
from common.logger import get_logger

RANDOM_STATE = 67
N_ITER = 30
TARGET = "price"
SERVICE_COLUMNS = {"id", "raw_id", "clean_laps_id"}
MODELS_DIR = Path(__file__).resolve().parent / "models"

logger = get_logger("ml.train")


def get_prepared_data() -> pl.DataFrame:
    """Завантажує підготовлені дані та приводить десяткові стовпці до Float64."""
    logger.info("Loading prepared training data from `laptops_clean`.")
    try:
        df = load_table_data("laptops_clean")
        df = df.with_columns(pl.col(pl.Decimal).cast(pl.Float64))
        logger.info(f"Loaded {df.height} rows; schema: {df.schema}.")
        return df
    except Exception as e:
        logger.error(f"Failed to load or prepare training data: {e}")
        raise


def select_features(df: pl.DataFrame):
    """Відокремлює ознаки від цільової змінної перед поділом даних."""
    logger.info("Selecting model features and target.")
    try:
        feature_columns = [
            col for col in df.columns
            if col not in SERVICE_COLUMNS | {TARGET}
        ]

        if "screen_height" in feature_columns:
            feature_columns.remove("screen_height")
        
        if not feature_columns:
            logger.warning(
                "No feature columns remain after excluding identifier and target columns."
            )
            raise ValueError

        X = (df.select(feature_columns)
           .with_columns(pl.col(pl.Boolean).cast(pl.Int8))
           .to_pandas())
        y = df[TARGET].to_numpy()
        logger.info(
            f"Selected {len(feature_columns)} features for {len(y)} rows."
        )
        return X, y
    except Exception as e:
        logger.error(f"Failed to select features and target: {e}")
        raise


def features_splitting(X, y):
    """Поділяє ознаки та цільову змінну на навчальну й тестову вибірки."""
    logger.info("Splitting data into training and test sets.")
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=RANDOM_STATE
        )

        logger.info(
            f"Data split successfully: {len(X_train)} training rows, "
            f"{len(X_test)} test rows."
        )
        return X_train, X_test, y_train, y_test
    except Exception as e:
        logger.error(f"Failed to split data into training and test sets: {e}")
        raise


def preprocessing_train__pipline(X_train):
    """Створює препроцесор для числових і категоріальних ознак."""
    logger.info("Building the training data preprocessor.")
    try:
        numeric_features = X_train.select_dtypes(
            include="number"
        ).columns.tolist()

        categorial_features = X_train.select_dtypes(
            exclude="number"
        ).columns.tolist()

        numeric_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler())
        ])

        categorical_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoding", OneHotEncoder(
                handle_unknown="infrequent_if_exist",
                min_frequency=10,
                sparse_output=False
            ))
        ])

        preprocessor = ColumnTransformer([
            ("num", numeric_pipeline, numeric_features),
            ("cat", categorical_pipeline, categorial_features)
        ])

        logger.info("Training data preprocessor created successfully.")
        return preprocessor
    
    except Exception as e:
        logger.error(f"Failed to build the training data preprocessor: {e}")
        raise


def make_pipline(estimator, preprocessor, model_name, log_target=True):
    """Створює конвеєр із препроцесором і заданою моделлю."""
    logger.info(f"Building model pipeline for {model_name}.")
    try:
        pipline = Pipeline([
            ("preprocessor", preprocessor),
            ("model", estimator)
        ])

        if log_target:
            logger.info(f"Model pipeline for {model_name} created successfully.")
            return TransformedTargetRegressor(
                regressor=pipline,
                func=np.log1p,
                inverse_func=np.expm1
            )

        logger.info(f"Model pipeline for {model_name} created successfully.")
        return pipline
    except Exception as e:
        logger.error(f"Failed to build the pipeline for {model_name}: {e}")
        raise


def build_models(preprocessor):
    """Створює словник базових моделей для навчання та порівняння."""
    logger.info("Building candidate model pipelines.")
    try:
        models = {
            "Dummy": make_pipline(
                DummyRegressor(strategy="mean"),
                preprocessor=preprocessor,
                model_name="Dummy",
                log_target=False,
            ),
            "LinearRegression": make_pipline(
                LinearRegression(),
                preprocessor=preprocessor,
                model_name="LinearRegression",
            ),
            "RandomForest": make_pipline(
                RandomForestRegressor(
                    n_estimators=200,
                    min_samples_leaf=2,
                    random_state=RANDOM_STATE,
                    n_jobs=1,
                ),
                preprocessor=preprocessor,
                model_name="RandomForest",
            ),
            "HistGradientBoosting": make_pipline(
                HistGradientBoostingRegressor(
                    learning_rate=0.1,
                    max_leaf_nodes=31,
                    min_samples_leaf=10,
                    max_iter=200,
                    l2_regularization=1.0,
                    random_state=RANDOM_STATE,
                ),
                preprocessor=preprocessor,
                model_name="HistGradientBoosting",
            ),
        }
        logger.info(f"Built {len(models)} model pipelines.")
        return models
    except Exception as e:
        logger.error(f"Failed to build candidate model pipelines: {e}")
        raise


def cross_validation(model, X_train, y_train, model_name):
    """Оцінює модель за допомогою п'ятиблокової перехресної перевірки."""
    logger.info(f"Starting cross-validation for {model_name}.")
    try:
        if len(X_train) < 5:
            logger.warning(
                "Five-fold cross-validation requires at least five training rows."
            )
            raise ValueError(
                "Five-fold cross-validation requires at least five training rows."
            )

        cv = KFold(
            n_splits=5,
            shuffle=True,
            random_state=RANDOM_STATE
        )

        scores = cross_validate(
            model,
            X_train,
            y_train,
            cv=cv,
            n_jobs=1,
            return_train_score=True,
            scoring={"rmse": "neg_root_mean_squared_error",
                 "mae": "neg_mean_absolute_error", "r2": "r2"},
        )

        logger.info(f"Cross-validation for {model_name} completed successfully.")
        return {
            "fold": list(range(1, len(scores["test_rmse"]) + 1)),
            "train_RMSE": (-scores["train_rmse"]).tolist(),
            "validation_RMSE": (-scores["test_rmse"]).tolist(),
            "train_MAE": (-scores["train_mae"]).tolist(),
            "validation_MAE": (-scores["test_mae"]).tolist(),
            "validation_R2": (scores["test_r2"]).tolist(),
        }
           
    except Exception as e:
        logger.error(f"Cross-validation for {model_name} failed: {e}")
        raise


def model_tuning(model, params, X_train, y_train, model_name):
    """Підбирає гіперпараметри моделі методом випадкового пошуку."""
    logger.info(f"Starting hyperparameter tuning for {model_name}.")
    try:
        search = RandomizedSearchCV(
            model,
            param_distributions=params,
            n_iter=N_ITER,
            scoring="neg_root_mean_squared_error",
            cv=KFold(
                5,
                shuffle=True,
                random_state=RANDOM_STATE,
            ),
            random_state=RANDOM_STATE,
            n_jobs=-1,
            refit=True,
        )
        search.fit(X_train, y_train)
        logger.info(
            f"Tuning for {model_name} completed. Best CV RMSE: "
            f"{-search.best_score_:.4f}."
        )
        return search
    except Exception as e:
        logger.error(f"Hyperparameter tuning for {model_name} failed: {e}")
        raise


def save_best_model(
    best_model,
    cv,
    searches,
    test_metrics,
    feature_columns,
    cat_columns,
    X_train,
    best_model_name="HistGradientBoosting",
):
    """Зберігає найкращу модель і метадані оцінювання."""
    logger.info(f"Saving best model and metrics for {best_model_name}.")
    try:
        
        joblib.dump(best_model, MODELS_DIR / "best_model.joblib")

        with open(MODELS_DIR / "metrics.json", "w", encoding="utf-8") as fh:
            json.dump({
                "cv_results": cv,
                "tuning": {n: {"cv_rmse": float(-s.best_score_), "best_params": s.best_params_} 
                           for n, s in searches.items()},
                "best_model_name": best_model_name,
                "test_metrics": test_metrics,
                "feature_columns": feature_columns,
                "categorial_columns": {c: sorted(X_train[c].dropna().unique().tolist()) for c in cat_columns}
            }, fh, ensure_ascii=False, indent=2)
        logger.info(f"Model and metrics saved to {MODELS_DIR}.")
    except Exception as e:
        logger.error(f"Failed to save model and metrics for {best_model_name}: {e}")
        raise


def main():
    """Виконує повний цикл навчання, оцінювання та збереження моделі."""
    logger.info("Starting model training workflow.")
    try:
        df = get_prepared_data()
        X, y = select_features(df=df)
        logger.info(
            f"Training data has {X.shape[0]} rows and {X.shape[1]} features; "
            f"missing values: {int(X.isna().sum().sum())}."
        )

        X_train, X_test, y_train, y_test = features_splitting(X=X, y=y)
        preprocessor = preprocessing_train__pipline(X_train=X_train)
        models = build_models(preprocessor=preprocessor)

        cv_results = {}
        for name, model in models.items():
            cv_results[name] = cross_validation(
                model=model,
                X_train=X_train,
                y_train=y_train,
                model_name=name,
            )
        

        hgb_params = {
            "regressor__model__learning_rate": [0.05],
            "regressor__model__max_iter": [600, 800, 1000],
            "regressor__model__max_leaf_nodes": [4, 6, 8, 10],
            "regressor__model__min_samples_leaf": [3, 5, 8],
            "regressor__model__l2_regularization": [0.0, 1.0, 5.0],
        }

        rf_params = {
            "regressor__model__n_estimators": [300, 600],
            "regressor__model__max_depth": [None, 12, 20],
            "regressor__model__min_samples_leaf": [1, 2, 4],
            "regressor__model__max_features": [0.5, 0.7, 1.0],
        }


        hgb_search = model_tuning(
            models["HistGradientBoosting"],
            hgb_params,
            X_train,
            y_train,
            "HistGradientBoosting",
        )

        rf_search = model_tuning(
            models["RandomForest"],
            rf_params,
            X_train,
            y_train,
            "RandomForest",
        )

        searches = {"HistGradientBoosting": hgb_search, "RandomForest": rf_search}
        best_name, best_search = max(searches.items(), key=lambda  kv: kv[1].best_score_)
        best_model = hgb_search.best_estimator_

        logger.info(f"Selected {best_name} by CV: {-best_search.best_score_:.0f}")

        y_pred = best_model.predict(X_test)

        logger.info(
            f"Prediction range: {y_pred.min():.0f}..{y_pred.max():.0f}; "
            f"actual range: {y_test.min():.0f}..{y_test.max():.0f}; "
            f"NaN predictions: {np.isnan(y_pred).sum()}."
        )
        test_metrics = {
            "rmse": float(np.sqrt(mean_squared_error(y_test, y_pred))),
            "mae": float(mean_absolute_error(y_test, y_pred)),
            "r2": float(r2_score(y_test, y_pred)),
            "mape": float(mean_absolute_percentage_error(y_test, y_pred)),
        }
        logger.info(f"Test metrics: {test_metrics}.")
    
        save_best_model(
            best_model=best_model,
            cv=cv_results,
            searches=searches,
            test_metrics=test_metrics,
            feature_columns=X_train.columns.tolist(),
            cat_columns=X_train.select_dtypes(exclude="number").columns.tolist(),
            X_train=X_train,
            best_model_name=best_name
        )
        X_test.assign(actual_price=y_test, predicted_price=y_pred).to_parquet(
            MODELS_DIR / "test_predictions.parquet", index=False)
        logger.info("Model training workflow completed successfully.")
        
    except Exception as e:
        logger.error(f"Model training workflow failed: {e}")
        raise


if __name__ == "__main__":
    main()



    

