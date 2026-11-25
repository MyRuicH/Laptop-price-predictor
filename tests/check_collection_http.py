"""Exercise Postman requests and validate live responses against openapi.yaml.

This uses urllib and JSON Schema; it does not execute Postman's JavaScript tests.
Run from the project root after starting the containers.
"""

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main(base_url=None):
    collection = json.loads((ROOT / "postman-collection.json").read_text(encoding="utf-8"))
    spec = yaml.safe_load((ROOT / "openapi.yaml").read_text(encoding="utf-8"))
    variables = {v["key"]: str(v["value"]) for v in collection["variable"]}
    if base_url:
        variables["baseUrl"] = base_url.rstrip("/")
    opener = urllib.request.build_opener(NoRedirect())
    count = 0

    def resolve(text):
        return re.sub(r"\{\{([^{}]+)\}\}", lambda match: variables[match[1]], text)

    for folder in collection["item"]:
        for item in folder["item"]:
            request = item["request"]
            method = request["method"]
            url = resolve(request["url"])
            path = urllib.parse.urlsplit(url).path
            tests = "\n".join(e["script"]["exec"][0] for e in item["event"] if e["listen"] == "test")
            expected = int(re.search(r"have\.status\((\d+)\)", tests)[1])
            raw = request.get("body", {}).get("raw")
            req = urllib.request.Request(
                url, method=method,
                data=resolve(raw).encode() if raw is not None else None,
                headers={h["key"]: resolve(h["value"]) for h in request["header"]},
            )
            try:
                response = opener.open(req, timeout=15)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                body = response.read()
                media = response.headers.get_content_type()
                assert response.status == expected, (item["name"], response.status, body)
                spec_path = "/static/{asset_path}" if path.startswith("/static/") else path
                documented = spec["paths"][spec_path][method.lower()]["responses"][str(expected)]
                if "$ref" in documented:
                    documented = spec["components"]["responses"][documented["$ref"].split("/")[-1]]
                if method == "HEAD":
                    assert body == b""
                elif "content" in documented:
                    assert media in documented["content"], (item["name"], media)
                    if media == "application/json":
                        data = json.loads(body)
                        schema = {**documented["content"][media]["schema"], "components": spec["components"]}
                        Draft202012Validator(schema).validate(data)
                if path == "/openapi.yaml":
                    assert body == (ROOT / "openapi.yaml").read_bytes()
                    assert yaml.safe_load(body) == spec
                elif path == "/openapi.json":
                    assert json.loads(body) == spec
                elif path in ("/docs/", "/redoc"):
                    assert b"/openapi.yaml" in body
                elif path == "/docs":
                    assert response.headers["Location"].endswith("/docs/")
                elif path == "/health":
                    assert json.loads(body)["status"] == variables["expectedHealthStatus"]
                elif path == "/api/predict" and expected == 200:
                    result = json.loads(body)
                    assert 0 < result["price_low"] <= result["predicted_price"] <= result["price_high"]
                    if item["name"] in ("Predict: opsys omitted", "Predict: opsys null", "Predict: opsys blank"):
                        assert len([w for w in result["warnings"] if w.startswith("Не вказано: opsys.")]) == 1
                    elif item["name"] == "Predict: legacy Unknown OS":
                        variables["legacyNoOsPrediction"] = str(result["predicted_price"])
                    elif item["name"] == "Predict: No OS alias":
                        assert result["predicted_price"] == float(variables["legacyNoOsPrediction"])
                count += 1
                print(f"OK {response.status} {method} {path}")
    print(f"Passed {count} collection HTTP requests and OpenAPI response validation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    main(parser.parse_args().base_url)
