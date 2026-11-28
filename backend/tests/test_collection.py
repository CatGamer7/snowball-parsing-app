"""SNO-27: deterministic collection tests; no VK, model downloads or pytest plugins."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.schemas import StartRequest
from core.jobs import CollectionJobStore
from services import collection
from services.ner import GLINER_ID, MLInferenceError, MLNotAvailable
from vk.client import VKAPIError
from vk.models import VKGroup, VKPost, VKUser


def post(number=1, text="Tomsk", owner=-1):
    return VKPost(id=f"{owner}_{number}", owner_id=owner, text=text, date=1)


def entity(text="Tomsk", score=0.9):
    return {"text": text, "score": score}


class FakeClient:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.requests_count = 0
        self.calls = []
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def call(self, method, **params):
        self.requests_count += 1
        self.calls.append((method, params))
        result = self.responses.get((method, params.get("q", params.get("owner_id"))), [])
        if isinstance(result, Exception):
            raise result
        return {"items": [
            {"id": int(p.id.split("_")[1]), "owner_id": p.owner_id,
             "text": p.text, "date": p.date} for p in result
        ]}


class FakeExtractor:
    def __init__(self, outputs=None, failure=None):
        self.outputs = outputs or {}
        self.failure = failure
        self.calls = []

    def validate_models(self, models):
        if isinstance(self.failure, MLNotAvailable):
            raise self.failure

    def extract(self, text, labels, threshold):
        self.calls.append((text, labels, threshold))
        if self.failure:
            raise self.failure
        return self.outputs.get(text, [])


class EntitySelectionTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(collection.normalize_entity("  Ｔomsk\t CITY  "),
                         ("tomsk city", "Tomsk CITY"))

    def test_frequency_is_per_post_not_per_mention(self):
        outputs = [[entity("Z"), entity("Z"), entity("a")], [entity("A")]]
        self.assertEqual(collection.select_entities(outputs, set(), .5, 1), [("a", "a")])

    def test_tie_is_alphabetical(self):
        self.assertEqual(collection.select_entities([[entity("Z"), entity("A")]], set(), .5, 2),
                         [("a", "A"), ("z", "Z")])

    def test_filters_used_blank_long_and_low_score(self):
        outputs = [[entity("Used"), entity(" "), entity("x" * 101), entity("low", .49),
                    entity("edge", .5), entity("y" * 100)]]
        self.assertEqual(collection.select_entities(outputs, {"used"}, .5, 3),
                         [("edge", "edge"), ("y" * 100, "y" * 100)])

    def test_threshold_endpoints(self):
        for threshold in (0, 1):
            with self.subTest(threshold=threshold):
                self.assertEqual(collection.select_entities([[entity("x", threshold)]],
                                                           set(), threshold, 1), [("x", "x")])

    def test_bad_model_output(self):
        invalid = [None, {}, [None], [{}], [{"text": 3, "score": .9}],
                   [entity(score=".9")], [entity(score=None)], [entity(score=float("nan"))],
                   [entity(score=float("inf"))], [entity(score=-.1)], [entity(score=1.1)]]
        for output in invalid:
            with self.subTest(output=output), self.assertRaises(MLInferenceError):
                collection.select_entities([output], set(), .5, 1)


class CollectionTests(unittest.IsolatedAsyncioTestCase):
    async def run_job(self, seeds=None, outputs=None, responses=None, failure=None, cap=5000,
                      **rules):
        self.store = CollectionJobStore()
        self.job = self.store.create(vk_requests_count=3)
        self.client = FakeClient(responses)
        self.extractor = FakeExtractor(outputs, failure)
        request = StartRequest.model_validate({
            "token": "test-only-token", "seeds": [{"type": "post", "id": "-1_1"}],
            "rules": {"models": {GLINER_ID: {"labels": ["city"]}}, "threshold": .5,
                      "max_depth": 2, **rules},
        })
        with patch.object(collection, "MAX_RECORDS", cap):
            await asyncio.wait_for(collection.run_collection(
                self.job.collection_id, [post()] if seeds is None else seeds, 3, request,
                store=self.store, client_factory=lambda token: self.client,
                extractor=self.extractor,
            ), timeout=5)
        progress = self.store.get(self.job.collection_id)
        self.assertEqual(progress.vk_requests_count, 3 + self.client.requests_count)
        self.assertIsNotNone(progress.started_at)
        self.assertIsNotNone(progress.finished_at)
        self.assertGreaterEqual(progress.finished_at, progress.started_at)
        self.assertTrue(self.client.closed)
        return progress

    def assert_completed(self, progress, reason, count, level):
        self.assertEqual((progress.status, progress.stop_reason, progress.records_count,
                          progress.expansion_level), ("completed", reason, count, level))
        self.assertIsNone(progress.error)

    async def test_no_text_records(self):
        result = await self.run_job(seeds=[post(text="  ")])
        self.assert_completed(result, "no_text_records", 0, 0)
        self.assertEqual(self.extractor.calls, [])

    async def test_no_new_entities(self):
        self.assert_completed(await self.run_job(), "no_new_entities", 1, 0)

    async def test_no_new_records(self):
        result = await self.run_job(outputs={"Tomsk": [entity()]},
                                    responses={("newsfeed.search", "Tomsk"): [post()]})
        self.assert_completed(result, "no_new_records", 1, 1)
        self.assertEqual(self.client.calls, [("newsfeed.search", {
            "q": "Tomsk", "count": 20, "extended": 1,
            "fields": "description,members_count,screen_name"})])

    async def test_max_depth(self):
        result = await self.run_job(outputs={"Tomsk": [entity()]}, max_depth=1,
                                    responses={("newsfeed.search", "Tomsk"): [post(2)]})
        self.assert_completed(result, "max_depth", 2, 1)

    async def test_record_limit_during_search(self):
        result = await self.run_job(outputs={"Tomsk": [entity()]}, cap=2,
                                    responses={("newsfeed.search", "Tomsk"): [post(2), post(3)]})
        self.assert_completed(result, "record_limit", 2, 1)

    async def test_record_limit_in_seeds_skips_ml(self):
        result = await self.run_job(seeds=[post(1), post(2), post(3)], cap=2)
        self.assert_completed(result, "record_limit", 2, 0)
        self.assertEqual(self.extractor.calls, [])

    async def test_load_group_and_user_walls(self):
        result = await self.run_job(
            seeds=[VKGroup(id="12", name="group"),
                   VKUser(id="34", first_name="A", last_name="B")],
            responses={("wall.get", -12): [post(1)], ("wall.get", 34): [post(2)]})
        self.assert_completed(result, "no_new_entities", 2, 0)
        self.assertEqual([params["owner_id"] for _, params in self.client.calls], [-12, 34])
        self.assertTrue(all(params["count"] == 100 for _, params in self.client.calls))

    async def test_deduplication_and_blank_filter(self):
        result = await self.run_job(seeds=[post(1), post(1), post(2, " "), post(3)])
        self.assert_completed(result, "no_new_entities", 2, 0)
        total, records = self.store.get_records(self.job.collection_id, offset=0, limit=20)
        self.assertEqual(total, 2)
        self.assertEqual([record.id for record in records], ["-1_1", "-1_3"])

    async def test_used_queries_and_cached_inference(self):
        result = await self.run_job(outputs={"Tomsk": [entity()]},
                                    responses={("newsfeed.search", "Tomsk"): [post(2)]})
        self.assert_completed(result, "no_new_entities", 2, 1)
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(len(self.extractor.calls), 2)

    async def test_new_entities_expand_second_level(self):
        result = await self.run_job(outputs={"Tomsk": [entity()], "Omsk": [entity("Omsk")]},
                                    responses={("newsfeed.search", "Tomsk"): [post(2, "Omsk")],
                                               ("newsfeed.search", "Omsk"): [post(3, "new")]})
        self.assert_completed(result, "max_depth", 3, 2)
        self.assertEqual([params["q"] for _, params in self.client.calls], ["Tomsk", "Omsk"])

    async def test_sample_size_and_text_truncation(self):
        await self.run_job(seeds=[post(i, str(i) * 5000) for i in range(1, 6)], sample_size=2)
        first = list(self.extractor.calls)
        self.assertEqual(len(first), 2)
        self.assertTrue(all(len(text) == 4000 for text, _, _ in first))
        self.assertTrue(all(labels == ["city"] and threshold == .5 for _, labels, threshold in first))
        await self.run_job(seeds=[post(i, str(i) * 5000) for i in range(1, 6)], sample_size=2)
        self.assertEqual(self.extractor.calls, first)

    async def test_top_entities_limits_searches(self):
        result = await self.run_job(outputs={"Tomsk": [entity("Z"), entity("A")]}, top_entities=1)
        self.assert_completed(result, "no_new_records", 1, 1)
        self.assertEqual(result.selected_entities_count, 1)
        self.assertEqual([params["q"] for _, params in self.client.calls], ["A"])

    async def test_ml_failures(self):
        for failure, code in [(MLNotAvailable("unavailable"), "ML_NOT_AVAILABLE"),
                              (MLInferenceError("bad model"), "ML_ERROR"),
                              (RuntimeError("unexpected"), "INTERNAL_ERROR")]:
            with self.subTest(code=code):
                result = await self.run_job(failure=failure)
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.error.code, code)
                self.assertEqual(result.records_count, 1)
                self.assertIsNone(result.stop_reason)

    async def test_malformed_ml_output(self):
        result = await self.run_job(outputs={"Tomsk": [entity(score=float("nan"))]})
        self.assertEqual((result.status, result.error.code), ("failed", "ML_ERROR"))

    async def test_vk_failures_preserve_partial_records(self):
        for failure in [VKAPIError(6, "quota"), httpx.ConnectError("offline"),
                        ValueError("malformed VK response")]:
            with self.subTest(failure=type(failure).__name__):
                result = await self.run_job(outputs={"Tomsk": [entity()]},
                                            responses={("newsfeed.search", "Tomsk"): failure})
                self.assertEqual((result.status, result.error.code), ("failed", "VK_ERROR"))
                self.assertEqual(result.records_count, 1)
                self.assertNotIn("test-only-token", result.model_dump_json())


if __name__ == "__main__":
    unittest.main()
