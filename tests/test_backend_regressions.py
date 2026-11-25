"""Перевірки виправлень без читання .env, БД або перенавчання моделі."""

import importlib
import logging
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import polars as pl
from pydantic import ValidationError

# Забороняємо dotenv читати файли під час імпорту модулів застосунку.
with patch("dotenv.load_dotenv", return_value=False):
    db_con = importlib.import_module("backend.db_con")
    features = importlib.import_module("etl.features")
    from backend.model_loader import ModelService
    from backend.schemas import LaptopInput

ROOT = Path(__file__).resolve().parents[1]


class ModelRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = ModelService.load(ROOT / "ml" / "models")
        cls.test_data = pd.read_parquet(ROOT / "ml" / "models" / "test_predictions.parquet")
        for _, row in cls.test_data.iterrows():
            data = {k: row[k] for k in LaptopInput.model_fields if k in row.index}
            try:
                cls.payload = LaptopInput(**data)
                break
            except ValidationError:
                continue

    def test_missing_opsys_has_one_warning_and_uses_nan(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                payload = LaptopInput(**{**self.payload.model_dump(), "opsys": value})
                warnings = self.service.check_options(payload)
                missing = [w for w in warnings if w.startswith("Не вказано: opsys.")]
                self.assertEqual(len(missing), 1)
                self.assertIsNone(payload.opsys)
                self.assertTrue(pd.isna(self.service.build_input(payload).iloc[0]["opsys"]))

    def test_no_os_uses_existing_model_category_without_retraining(self):
        for value in ("No OS", "No Os", " no os "):
            with self.subTest(value=value):
                payload = LaptopInput(**{**self.payload.model_dump(), "opsys": value})
                self.assertEqual(payload.opsys, "No OS")
                self.service.check_options(payload)
                frame = self.service.build_input(payload)
                self.assertEqual(frame.iloc[0]["opsys"], "Unknown")
                legacy = LaptopInput(**{**self.payload.model_dump(), "opsys": "Unknown"})
                pd.testing.assert_frame_equal(frame, self.service.build_input(legacy))

    def test_options_include_no_os_without_mutating_saved_options(self):
        original = list(self.service.options["dropdowns"]["opsys"])
        self.assertIn("No OS", self.service.options_payload()["dropdowns"]["opsys"])
        self.assertEqual(self.service.options["dropdowns"]["opsys"], original)

    def test_serving_reproduces_saved_predictions(self):
        frames, expected, rejected = [], [], 0
        for _, row in self.test_data.iterrows():
            data = {k: row[k] for k in LaptopInput.model_fields if k in row.index}
            try:
                payload = LaptopInput(**data)
            except ValidationError:
                rejected += 1
                continue
            self.service.check_options(payload)
            frames.append(self.service.build_input(payload))
            expected.append(float(row["predicted_price"]))
        self.assertEqual(rejected, 4)
        np.testing.assert_allclose(
            self.service.model.predict(pd.concat(frames, ignore_index=True)),
            expected, rtol=1e-12, atol=1e-8,
        )


class EtlRegressionTests(unittest.TestCase):
    def test_no_os_variants_are_preserved_as_one_category(self):
        data = pl.DataFrame({
            "company": ["Lenovo"] * 5,
            "type_name": ["Notebook"] * 5,
            "opsys": ["No OS", "No Os", " no os ", "Unknown", "Windows 10"],
            "cpu_brand": ["Intel"] * 5,
            "gpu_brand": ["Intel"] * 5,
        })
        result = features.normalize_categoricals(data)
        self.assertEqual(
            result["opsys"].to_list(),
            ["No OS", "No OS", "No OS", "Unknown", "Windows 10"],
        )


class DatabaseRegressionTests(unittest.TestCase):
    def test_connection_uses_separate_environment_arguments(self):
        config = {
            "DB_HOST": "postgres", "DB_PORT": "5432", "DB_NAME": "test_laptops",
            "DB_USER": "test_user", "DB_PASSWORD": "test-@%#",
        }
        with patch.dict(os.environ, config, clear=True), patch.object(db_con.psycopg2, "connect") as connect:
            db_con.get_connection(connect_timeout=2)
        connect.assert_called_once_with(
            host="postgres", port="5432", dbname="test_laptops",
            user="test_user", password="test-@%#", connect_timeout=2,
        )

    def test_prediction_is_saved_as_json_number(self):
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        with patch.object(db_con, "get_connection", return_value=conn):
            db_con.save_prediction({"opsys": "No OS"}, 57000.0)
        sql, params = cursor.execute.call_args.args
        self.assertIn("pridicted_price", sql)
        self.assertEqual(params[0].adapted, {"opsys": "No OS"})
        self.assertEqual(params[1].adapted, 57000.0)
        conn.close.assert_called_once()

    def test_database_outage_does_not_break_prediction_logging(self):
        with patch.object(db_con, "get_connection", side_effect=RuntimeError("test outage")):
            self.assertIsNone(db_con.save_prediction({"opsys": None}, 57000.0))
            self.assertFalse(db_con.check_db())


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    unittest.main()
