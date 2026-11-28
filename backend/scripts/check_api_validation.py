"""SNO-16: explicit live checks against a running backend, without mocks or ML."""
import argparse
from copy import deepcopy
import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


# Only a deliberately invalid token is sent; no real credentials are required.
CASES = [
    ("VAL-04", "POST", "/vk/validate", '{"token":"vk1.a.wrong"}', 401, "INVALID_TOKEN"),
    ("VAL-06", "POST", "/vk/validate", '{"token":""}', 422, "VALIDATION_ERROR"),
    ("VAL-07", "POST", "/vk/validate", '{"token":"   "}', 422, "VALIDATION_ERROR"),
    ("VAL-08", "POST", "/vk/validate", '{}', 422, "VALIDATION_ERROR"),
    ("VAL-09/number", "POST", "/vk/validate", '{"token":123}', 422, "VALIDATION_ERROR"),
    ("VAL-09/null", "POST", "/vk/validate", '{"token":null}', 422, "VALIDATION_ERROR"),
    ("VAL-10", "POST", "/vk/validate", '{"token":"x","a":1}', 422, "VALIDATION_ERROR"),
    ("VAL-11", "POST", "/vk/validate", 'abc', 422, "VALIDATION_ERROR"),
    ("MOD-08", "POST", "/collection/models", '{}', 405, None),
    ("GEN-01", "GET", "/no-such", None, 404, None),
    ("GEN-02", "GET", "/vk/validate", None, 405, None),
]


def start_cases() -> list:
    gliner = "urchade/gliner_multi-v2.1"
    wiki = "Babelscape/wikineural-multilingual-ner"
    base = {
        "token": "vk1.a.wrong",
        "seeds": [{"type": "group", "id": "vk"}],
        "rules": {"models": {gliner: {"labels": ["city"]}},
                  "threshold": 0.5, "max_depth": 2},
    }
    cases = []
    missing = object()

    def add(case_id, path, value=missing, status=422, code="VALIDATION_ERROR"):
        payload = deepcopy(base)
        if not path:
            payload = value
        else:
            parent = payload
            for key in path[:-1]:
                parent = parent[key]
            if value is missing:
                del parent[path[-1]]
            else:
                parent[path[-1]] = value
        cases.append((case_id, "POST", "/collection/start", json.dumps(payload), status, code))

    add("STA-10", (), base, 401, "INVALID_TOKEN")
    add("STA-12", ("rules", "models"), {"unknown/model": {}}, 404, "MODEL_NOT_FOUND")
    add("STA-13", ("rules", "models"), {})
    add("STA-14/missing", ("rules", "models"), {gliner: {}})
    add("STA-14/empty", ("rules", "models"), {gliner: {"labels": []}})
    add("STA-15/duplicates", ("rules", "models"), {gliner: {"labels": ["city", "city"]}})
    add("STA-15/blank", ("rules", "models"), {gliner: {"labels": ["   "]}})
    add("STA-16", ("rules", "models"), {wiki: {"labels": ["city"]}})
    for label, value in [("negative", -0.01), ("above-one", 1.01), ("string", "0.5")]:
        add(f"STA-17/{label}", ("rules", "threshold"), value)
    add("STA-17/missing", ("rules", "threshold"))
    for label, value in [("zero", 0), ("above-five", 6), ("fraction", 1.5)]:
        add(f"STA-18/{label}", ("rules", "max_depth"), value)
    add("STA-19/empty", ("seeds",), [])
    add("STA-19/missing", ("seeds",))
    for label, seed in [
        ("type", {"type": "chat", "id": "1"}),
        ("empty-id", {"type": "group", "id": ""}),
        ("blank-id", {"type": "group", "id": "  "}),
        ("extra", {"type": "group", "id": "vk", "extra": 1}),
    ]:
        add(f"STA-20/{label}", ("seeds",), [seed])
    for label, value in [("number", "123"), ("letters", "abc_def")]:
        add(f"STA-21/{label}", ("seeds",), [{"type": "post", "id": value}])
    add("STA-23", ("rules",), {"model_id": gliner, "threshold": 0.5, "max_depth": 2})
    add("STA-24/root", ("extra",), 1)
    add("STA-24/rules", ("rules", "extra"), 1)
    add("STA-27", (), {})
    for case_id, field, values in [
        ("STA-28", "sample_size", [0, 1001]),
        ("STA-29", "top_entities", [0, 21]),
    ]:
        for value in values:
            add(f"{case_id}/{value}", ("rules", field), value)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--section", choices=["validation", "start", "all"], default="validation")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    # Calls to a local backend should not go through system HTTP proxies.
    opener = build_opener(ProxyHandler({}))
    passed = 0
    cases = []
    if args.section in {"validation", "all"}:
        cases.extend(CASES)
    if args.section in {"start", "all"}:
        cases.extend(start_cases())
        print("NOTE: STA-17/string checks a known schema discrepancy; its FAIL must be investigated.")

    for case_id, method, path, body, expected_status, expected_code in cases:
        request = Request(
            base_url + path, method=method,
            data=body.encode("utf-8") if body is not None else None,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            try:
                response = opener.open(request, timeout=20)
            except HTTPError as exc:
                response = exc
            with response:
                status = response.getcode()
                payload = json.loads(response.read())
            error = payload.get("error") if isinstance(payload, dict) else None
            code = error.get("code") if isinstance(error, dict) else None
            success = status == expected_status and (expected_code is None or code == expected_code)
            passed += int(success)
            print(f"{'PASS' if success else 'FAIL'} {case_id}: HTTP {status}, code={code or '-'}")
            if not success:
                print(f"  Expected: HTTP {expected_status}, code={expected_code or '-'}")
        except (URLError, OSError):
            print(f"FAIL {case_id}: backend connection failed or timed out")
        except (ValueError, TypeError):
            print(f"FAIL {case_id}: invalid JSON response")

    failed = len(cases) - passed
    print(f"RESULT: {passed} passed, {failed} failed ({len(cases)} requests)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
