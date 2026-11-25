"""Завантаження ручної специфікації, спільної для Swagger UI та OpenAPI JSON."""

from functools import lru_cache
from pathlib import Path

import yaml

OPENAPI_FILE = Path(__file__).resolve().parents[1] / "openapi.yaml"


@lru_cache(maxsize=1)
def load_openapi_schema() -> dict:
    """Читає YAML один раз; зміни специфікації потребують перезапуску сервера."""
    with OPENAPI_FILE.open(encoding="utf-8") as source:
        schema = yaml.safe_load(source)
    if not isinstance(schema, dict) or schema.get("openapi") != "3.1.0":
        raise RuntimeError("openapi.yaml must contain an OpenAPI 3.1.0 document")
    return schema
