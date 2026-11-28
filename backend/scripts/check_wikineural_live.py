"""SNO-16 / STA-03: real VK collection must report unsupported WikiNEuRal."""
import argparse
import getpass
import json
import time
import warnings
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


BASE_URL = "http://127.0.0.1:8000"


class CheckFailure(Exception):
    pass


def run(token: str, group: str) -> None:
    opener = build_opener(ProxyHandler({}))

    def request(method, path, body=None):
        req = Request(
            BASE_URL + path, method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with opener.open(req, timeout=20) as response:
                return response.getcode(), json.loads(response.read())
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise CheckFailure(f"{method} {path}: HTTP {status}") from None
        except (URLError, OSError):
            raise CheckFailure("Backend connection failed or timed out") from None
        except ValueError:
            raise CheckFailure("Backend returned invalid JSON") from None

    status, started = request("POST", "/collection/start", {
        "token": token,
        "seeds": [{"type": "group", "id": group}],
        "rules": {"models": {"Babelscape/wikineural-multilingual-ner": {}},
                  "threshold": 0.5, "max_depth": 1, "sample_size": 1, "top_entities": 1},
    })
    collection_id = started.get("collection_id") if isinstance(started, dict) else None
    if (not isinstance(started, dict) or status != 202 or started.get("status") != "running"
            or not isinstance(collection_id, str) or not collection_id):
        raise CheckFailure("Unexpected collection start response")
    print("PASS start: HTTP 202, task accepted")
    print(f"Collection ID: {collection_id}")

    deadline = time.monotonic() + 60
    previous = None
    while time.monotonic() < deadline:
        status, progress = request("GET", f"/collection/{collection_id}/progress")
        if status != 200 or not isinstance(progress, dict) or progress.get("collection_id") != collection_id:
            raise CheckFailure("Unexpected progress response")
        state = progress.get("status")
        current = (state, progress.get("records_count"))
        if current != previous:
            print(f"Progress: status={state}, records={current[1]}")
            previous = current
        if state in {"completed", "failed"}:
            break
        if state not in {"queued", "running"}:
            raise CheckFailure("Unknown collection status")
        time.sleep(1)
    else:
        raise CheckFailure("Task did not finish within 60 seconds; it may still be running")

    error = progress.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    if state != "failed" or code != "ML_NOT_AVAILABLE":
        safe_code = code if code in {"ML_ERROR", "VK_ERROR", "INTERNAL_ERROR"} else "unexpected"
        raise CheckFailure(f"Expected failed / ML_NOT_AVAILABLE; got {state} / {safe_code}")
    print("PASS progress: failed / ML_NOT_AVAILABLE (expected for WikiNEuRal)")

    status, records = request("GET", f"/collection/{collection_id}/records?offset=0&limit=3")
    if status != 200 or not isinstance(records, dict) or records.get("collection_id") != collection_id:
        raise CheckFailure("Unexpected records response")
    total, items = records.get("total"), records.get("items")
    if not isinstance(total, int) or total < 1 or total != progress.get("records_count"):
        raise CheckFailure("Partial records missing or counts do not match")
    if not isinstance(items, list) or not items or len(items) > 3:
        raise CheckFailure("Partial records page missing or invalid")
    if any(not isinstance(item, dict) or not isinstance(item.get("text"), str)
           or not item["text"].strip() for item in items):
        raise CheckFailure("Returned page contains records without text")
    print(f"PASS records: HTTP 200, total={total}, returned={len(items)}; partial posts preserved")
    print("RESULT: WikiNEuRal API scenario passed; successful GLiNER collection was not tested")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="vk", help="Public starting group (default: vk)")
    args = parser.parse_args()
    if not args.group.strip():
        parser.error("group must not be blank")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("VK service key (hidden input): ").strip()
        if not token:
            raise CheckFailure("No key entered")
        run(token, args.group.strip())
        return 0
    except (getpass.GetPassWarning, EOFError):
        print("FAIL: cannot read the key securely; use an interactive terminal")
    except CheckFailure as exc:
        print(f"FAIL: {exc}")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
