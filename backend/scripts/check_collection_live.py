"""SNO-27: live run_collection check; run from backend with -m scripts.check_collection_live."""
import argparse
import asyncio
import getpass
import json
import logging
import time
import warnings

from api.collection_routes import load_seeds
from api.schemas import StartRequest
from core.jobs import CollectionJobStore
from services.collection import normalize_entity, run_collection
from services.ner import GLINER_ID
from vk.client import VKClient
from vk.source import VKDataSource


class TrackedClient(VKClient):
    def __init__(self, token):
        super().__init__(token)
        self.queries = []
        self.closed = False

    async def call(self, method, **params):
        if method == "newsfeed.search":
            self.queries.append(normalize_entity(params["q"])[0])
        return await super().call(method, **params)

    async def close(self):
        await super().close()
        self.closed = True


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS " + message, flush=True)


async def run(token, group):
    request = StartRequest.model_validate({
        "token": token,
        "seeds": [{"type": "group", "id": group}],
        "rules": {
            "models": {GLINER_ID: {
                "labels": ["person", "organization", "city", "country"],
            }},
            "threshold": 0.5, "max_depth": 2, "sample_size": 3, "top_entities": 1,
        },
    })
    async with VKClient(token) as seed_client:
        seeds = await load_seeds(VKDataSource(seed_client), request)
        initial_requests = seed_client.requests_count
    store = CollectionJobStore()
    job = store.create(vk_requests_count=initial_requests)
    client = TrackedClient(token)
    print("Running real VK + GLiNER: depth=2, sample_size=3, top_entities=1", flush=True)
    started = time.monotonic()
    await run_collection(job.collection_id, seeds, initial_requests, request,
                         store=store, client_factory=lambda _: client)
    elapsed = time.monotonic() - started
    progress = store.get(job.collection_id)
    print(json.dumps({
        "status": progress.status,
        "records_count": progress.records_count,
        "expansion_level": progress.expansion_level,
        "stop_reason": progress.stop_reason,
        "error_code": progress.error.code if progress.error else None,
        "vk_requests_count": progress.vk_requests_count,
        "elapsed_seconds": round(elapsed, 1),
    }, indent=2), flush=True)
    check(client.closed, "collection VK client closed")
    check(progress.status == "completed", "collection completed successfully")
    check(progress.error is None, "no collection error")
    check(progress.started_at is not None and progress.finished_at is not None
          and progress.started_at <= progress.finished_at, "ordered timestamps")
    check(0 <= progress.expansion_level <= 2, "depth does not exceed two")
    check(len(client.queries) == len(set(client.queries)), "no repeated search queries")
    check(len(client.queries) == progress.expansion_level,
          "one search per completed expansion level")
    check(client.requests_count == 1 + len(client.queries),
          "collection VK calls equal one wall request plus searches")
    check(progress.vk_requests_count == initial_requests + client.requests_count,
          "VK counter includes initial seed lookup")
    total, records = store.get_records(job.collection_id, offset=0, limit=5000)
    check(total == len(records) == progress.records_count, "stored count matches progress")
    check(0 < total <= 140, "nonempty records within 100 wall + 2 x 20 search bound")
    check(len({post.key for post in records}) == total, "record keys are unique")
    check(all(post.text.strip() for post in records), "no blank post text")
    check(progress.stop_reason in {"max_depth", "no_new_entities", "no_new_records"},
          "expected stop reason for bounded collection")
    check(progress.stop_reason != "max_depth" or progress.expansion_level == 2,
          "max_depth requires two completed levels")
    if progress.expansion_level < 2:
        print("INCONCLUSIVE: valid early stop; two-level expansion was not reached.")
        return 2
    print("RESULT: real collection module + VK + GLiNER passed through two levels")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="vk", help="Public group ID or short name")
    args = parser.parse_args()
    # Do not emit raw third-party request logs or exception messages with secrets.
    logging.disable(logging.CRITICAL)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("VK service key (hidden input): ").strip()
        if not token:
            print("FAIL: empty key")
            return 1
        return asyncio.run(run(token, args.group))
    except KeyboardInterrupt:
        print("Interrupted")
        return 130
    except Exception as exc:
        print("FAIL: " + type(exc).__name__)
        print("Raw exception details omitted to protect the key.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
