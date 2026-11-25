"""Перевірка ручного контракту та Postman-колекції без читання .env."""

import importlib
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from openapi_spec_validator import validate

with patch("dotenv.load_dotenv", return_value=False):
    main = importlib.import_module("backend.main")
    from backend.api_docs import load_openapi_schema
    from backend.schemas import LaptopInput

ROOT = Path(__file__).resolve().parents[1]


class OpenApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = load_openapi_schema()
        cls.collection = json.loads((ROOT / "postman-collection.json").read_text(encoding="utf-8"))

    def test_openapi_document_is_valid_and_used_by_app(self):
        validate(self.spec)
        self.assertIs(main.app.openapi(), self.spec)
        self.assertEqual(main.API_VERSION, self.spec["info"]["version"])

    def test_prediction_fields_and_bounds_match_runtime_schema(self):
        documented = self.spec["components"]["schemas"]["LaptopInput"]
        runtime = LaptopInput.model_json_schema()
        self.assertEqual(set(documented["properties"]), set(runtime["properties"]))
        self.assertEqual(set(documented["required"]), set(runtime["required"]))
        self.assertFalse(documented["additionalProperties"])
        for name in ("inches", "screen_width", "cpu_ghz", "ram_gb", "storage_gb", "weight"):
            for bound in ("minimum", "maximum"):
                self.assertEqual(documented["properties"][name][bound], runtime["properties"][name][bound])

    def test_documented_valid_example_passes_schema_and_pydantic(self):
        example = self.spec["components"]["schemas"]["LaptopInput"]["examples"][0]
        Draft202012Validator(self.spec["components"]["schemas"]["LaptopInput"]).validate(example)
        LaptopInput(**example)

    def test_every_http_route_and_static_mount_is_documented(self):
        routes = list(main.app.routes) + list(main.router.routes)
        for route in routes:
            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path and methods:
                self.assertIn(path, self.spec["paths"], path)
                for method in methods:
                    self.assertIn(method.lower(), self.spec["paths"][path], (method, path))
        self.assertIn("/static/{asset_path}", self.spec["paths"])
        self.assertIn("head", self.spec["paths"]["/static/{asset_path}"])

    def test_postman_variables_resolve_and_all_requests_have_assertions(self):
        variables = {v["key"]: v["value"] for v in self.collection["variable"]}
        self.assertEqual(variables["baseUrl"], "http://localhost:8000")
        self.assertFalse(any("password" in key.lower() for key in variables))
        count = 0
        for folder in self.collection["item"]:
            for item in folder["item"]:
                count += 1
                serialized = json.dumps(item, ensure_ascii=False)
                for key in re.findall(r"\{\{([^{}]+)\}\}", serialized):
                    self.assertIn(key, variables, (item["name"], key))
                self.assertTrue(any(e["listen"] == "test" for e in item["event"]))
                raw = item["request"].get("body", {}).get("raw")
                if raw and "malformed JSON" not in item["name"]:
                    resolved = re.sub(r"\{\{([^{}]+)\}\}", lambda m: str(variables[m[1]]), raw)
                    payload = json.loads(resolved)
                    if folder["name"].startswith("02"):
                        LaptopInput(**payload)
        self.assertEqual(count, 25)


if __name__ == "__main__":
    unittest.main()
