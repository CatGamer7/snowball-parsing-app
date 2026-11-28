"""SNO-16: one real VK + GLiNER collection through the running backend."""
import argparse
import getpass
import json
import time
import warnings
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


class CheckFailure(Exception):
    pass


def run(token: str, group: str, wait_seconds: int) -> None:
    opener = build_opener(ProxyHandler({}))

    def request(method, path, body=None):
        req = Request(
            "http://127.0.0.1:8000" + path, method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with opener.open(req, timeout=30) as response:
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
        "token": token, "seeds": [{"type": "group", "id": group}],
        "rules": {"models": {"urchade/gliner_multi-v2.1": {
            "labels": ["person", "organization", "city"],
        }}, "threshold": 0.5, "max_depth": 1, "sample_size": 1, "top_entities": 1},
    })
    collection_id = started.get("collection_id") if isinstance(started, dict) else None
    if (status != 202 or not isinstance(started, dict) or started.get("status") != "running"
            or not isinstance(collection_id, str) or not collection_id):
        raise CheckFailure("Unexpected start response")
    print("PASS start: HTTP 202, GLiNER task accepted", flush=True)
    print(f"Collection ID: {collection_id}", flush=True)
    since = time.monotonic()
    last_print = since - 10
    previous = None
    while time.monotonic() - since < wait_seconds:
        status, progress = request("GET", f"/collection/{collection_id}/progress")
        if (status != 200 or not isinstance(progress, dict)
                or progress.get("collection_id") != collection_id):
            raise CheckFailure("Unexpected progress response")
        state = progress.get("status")
        current = (state, progress.get("records_count"), progress.get("expansion_level"))
        now = time.monotonic()
        if current != previous or now - last_print >= 10:
            print(f"Progress: status={state}, records={current[1]}, level={current[2]}, "
                  f"wait={int(now - since)}s", flush=True)
            previous, last_print = current, now
        if state in {"completed", "failed"}:
            break
        if state not in {"queued", "running"}:
            raise CheckFailure("Unknown collection status")
        time.sleep(1)
    else:
        raise CheckFailure("Waiting timed out; the task may still be running")

    if state == "failed":
        error = progress.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        safe_code = code if code in {"ML_NOT_AVAILABLE", "ML_ERROR", "VK_ERROR", "INTERNAL_ERROR"} else "unexpected"
        raise CheckFailure(f"Collection failed: {safe_code}")
    if progress.get("error") is not None or not progress.get("finished_at"):
        raise CheckFailure("Completed task has an error or no finish time")
    reason = progress.get("stop_reason")
    if reason not in {"max_depth", "no_new_entities", "no_new_records"}:
        raise CheckFailure("Unexpected stop reason for this small collection")
    print(f"PASS progress: completed, stop_reason={reason}")
    print(f"VK requests: {progress.get('vk_requests_count')}; selected entities: "
          f"{progress.get('selected_entities_count')}")

    status, records = request("GET", f"/collection/{collection_id}/records?offset=0&limit=3")
    if status != 200 or not isinstance(records, dict) or records.get("collection_id") != collection_id:
        raise CheckFailure("Unexpected records response")
    total, items = records.get("total"), records.get("items")
    if type(total) is not int or total < 1 or total != progress.get("records_count"):
        raise CheckFailure("No collected posts or inconsistent counters")
    if not isinstance(items, list) or not items or len(items) > 3:
        raise CheckFailure("Invalid records page")
    if any(not isinstance(item, dict) or item.get("source") != "vk" or item.get("kind") != "post"
           or not isinstance(item.get("text"), str) or not item["text"].strip() for item in items):
        raise CheckFailure("Invalid VK post or empty text on returned page")
    print(f"PASS records: HTTP 200, total={total}, returned={len(items)}")
    print("RESULT: real VK + GLiNER API collection passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="vk", help="Public starting group (default: vk)")
    parser.add_argument("--wait-seconds", type=int, default=300)
    args = parser.parse_args()
    if not args.group.strip() or not 1 <= args.wait_seconds <= 1800:
        parser.error("group must not be blank; wait-seconds must be between 1 and 1800")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("VK service key (hidden input): ").strip()
        if not token:
            raise CheckFailure("No key entered")
        run(token, args.group.strip(), args.wait_seconds)
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
