"""Read-only SNO-16 checks for a completed max_depth task with 2..100 posts."""
import argparse
from datetime import datetime
import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import UUID, uuid4


class CheckFailure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise CheckFailure(message)


def run(collection_id: str) -> int:
    opener = build_opener(ProxyHandler({}))
    root = f"/collection/{collection_id}"
    passed = failed = 0

    def get(path):
        req = Request("http://127.0.0.1:8000" + path, headers={"Accept": "application/json"})
        try:
            response = opener.open(req, timeout=20)
        except HTTPError as exc:
            response = exc
        with response:
            return response.getcode(), json.loads(response.read())

    def check(case_id, operation):
        nonlocal passed, failed
        try:
            result = operation()
            passed += 1
            print(f"PASS {case_id}")
            return result
        except CheckFailure as exc:
            print(f"FAIL {case_id}: {exc}")
        except (URLError, OSError):
            print(f"FAIL {case_id}: backend connection failed or timed out")
        except (ValueError, TypeError, KeyError):
            print(f"FAIL {case_id}: invalid response structure or timestamp")
        failed += 1
        return None

    def summary():
        print(f"RESULT: {passed} passed, {failed} failed ({passed + failed} checks)")
        return 1 if failed else 0

    def progress_check():
        status, body = get(root + "/progress")
        require(status == 200, f"HTTP {status}; task may be missing after a backend restart")
        require(isinstance(body, dict) and body.get("collection_id") == collection_id,
                "Wrong collection identity")
        require(body.get("status") == "completed" and body.get("stop_reason") == "max_depth",
                "Use a task completed with max_depth")
        require(body.get("error") is None, "Completed task has an error")
        total = body.get("records_count")
        require(type(total) is int and 2 <= total <= 100, "Use a task with 2..100 records")
        started_text, finished_text = body.get("started_at"), body.get("finished_at")
        require(isinstance(started_text, str) and isinstance(finished_text, str),
                "Start and finish timestamps must both be present")
        started = datetime.fromisoformat(started_text.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_text.replace("Z", "+00:00"))
        require(started.utcoffset() is not None and finished.utcoffset() is not None,
                "Timestamps must include time zones")
        require(finished >= started, "Finish time is earlier than start time")
        return total

    total = check("PRO-03/completed-dates", progress_check)
    if total is None:
        print("STOP: check the task ID and keep the original backend process running")
        return summary()
    print(f"Fixture: completed task with {total} records; only GET requests are sent")

    def page_check(query, offset, limit, reference=None):
        status, body = get(root + "/records" + query)
        require(status == 200, f"Unexpected HTTP {status}")
        require(isinstance(body, dict) and body.get("collection_id") == collection_id,
                "Wrong collection identity")
        require(body.get("total") == total and body.get("offset") == offset
                and body.get("limit") == limit, "Wrong pagination metadata")
        items = body.get("items")
        require(isinstance(items, list), "items is not an array")
        require(len(items) == max(0, min(limit, total - offset)), "Wrong page length")
        for item in items:
            require(isinstance(item, dict), "Post is not an object")
            require(item.get("source") == "vk" and item.get("kind") == "post", "Wrong post type")
            require(isinstance(item.get("id"), str) and bool(item["id"].strip()), "Missing post ID")
            require(type(item.get("owner_id")) is int and type(item.get("date")) is int,
                    "owner_id and date must be integers")
            require(isinstance(item.get("text"), str) and bool(item["text"].strip()), "Empty post text")
        require(len({item["id"] for item in items}) == len(items), "Duplicate post IDs")
        if reference is not None:
            require(items == reference[offset:offset + limit], "Page differs from the reference slice")
        return items

    # This completed task has at most 100 posts, so one maximum-size page is a full reference.
    reference = check("REC-04/limit-100-fields-unique", lambda: page_check("?limit=100", 0, 100))
    if reference is None:
        print("STOP: reference page could not be validated; dependent page checks were not run")
        return summary()
    check("REC-09/defaults-nonempty", lambda: page_check("", 0, 20, reference))
    check("REC-02/offset-1-limit-1", lambda: page_check("?offset=1&limit=1", 1, 1, reference))
    check("REC-10/last-partial-page", lambda: page_check(f"?offset={total - 1}&limit=3", total - 1, 3, reference))
    check("REC-03/end", lambda: page_check(f"?offset={total}", total, 20, reference))
    check("REC-03/beyond-end", lambda: page_check(f"?offset={total + 10}", total + 10, 20, reference))

    def error_check(path, expected_status, expected_code):
        status, body = get(path)
        require(status == expected_status, f"Expected HTTP {expected_status}, got {status}")
        error = body.get("error") if isinstance(body, dict) else None
        require(isinstance(error, dict) and error.get("code") == expected_code,
                f"Expected error.code={expected_code}")

    for query in ["offset=-1", "limit=0", "limit=101", "offset=abc", "limit=1.5"]:
        check(f"REC-05/{query}", lambda query=query: error_check(
            root + "/records?" + query, 422, "VALIDATION_ERROR"))
    missing = str(uuid4())
    check("PRO-05/unknown", lambda: error_check(
        f"/collection/{missing}/progress", 404, "COLLECTION_NOT_FOUND"))
    check("REC-06/unknown", lambda: error_check(
        f"/collection/{missing}/records", 404, "COLLECTION_NOT_FOUND"))
    return summary()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-id", type=UUID, required=True)
    args = parser.parse_args()
    return run(str(args.collection_id))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
