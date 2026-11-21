"""SNO-16: offline API checks for progress and collected records."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import collection_routes
from core.jobs import CollectionFailure, CollectionJobStore
from main import app
from vk.models import VKPost


class CollectionAPITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = CollectionJobStore()
        self.store_patch = patch.object(collection_routes, "job_store", self.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                       base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)
        self.job = self.store.create(vk_requests_count=3)
        self.path = f"/collection/{self.job.collection_id}"

    def add_posts(self):
        self.store.start(self.job.collection_id)
        self.store.add_records(self.job.collection_id, [
            VKPost(id=f"-1_{i}", owner_id=-1, text=f"post {i}", date=i)
            for i in range(1, 4)
        ], limit=5000)

    async def test_queued_progress(self):
        response = await self.client.get(self.path + "/progress")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["collection_id"], body["status"], body["records_count"],
                          body["vk_requests_count"]),
                         (self.job.collection_id, "queued", 0, 3))
        self.assertIsNone(body["started_at"])
        self.assertIsNone(body["finished_at"])

    async def test_running_and_completed_progress(self):
        self.add_posts()
        response = await self.client.get(self.path + "/progress")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "running")
        self.assertEqual(response.json()["records_count"], 3)
        self.store.finish(self.job.collection_id, stop_reason="max_depth")
        response = await self.client.get(self.path + "/progress")
        body = response.json()
        self.assertEqual((body["status"], body["stop_reason"]), ("completed", "max_depth"))
        self.assertIsNotNone(body["started_at"])
        self.assertIsNotNone(body["finished_at"])
        self.assertIsNone(body["error"])

    async def test_failed_progress_and_partial_records(self):
        self.add_posts()
        self.store.finish(self.job.collection_id, CollectionFailure(code="ML_ERROR", message="test"))
        response = await self.client.get(self.path + "/progress")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "failed")
        self.assertEqual(response.json()["error"]["code"], "ML_ERROR")
        response = await self.client.get(self.path + "/records")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 3)

    async def test_unknown_collection(self):
        for endpoint in ("progress", "records"):
            with self.subTest(endpoint=endpoint):
                response = await self.client.get(f"/collection/missing/{endpoint}")
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["error"]["code"], "COLLECTION_NOT_FOUND")

    async def test_empty_records_and_defaults(self):
        response = await self.client.get(self.path + "/records")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"collection_id": self.job.collection_id,
                                          "total": 0, "offset": 0, "limit": 20, "items": []})

    async def test_pagination_and_record_fields(self):
        self.add_posts()
        response = await self.client.get(self.path + "/records?offset=1&limit=1")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["total"], body["offset"], body["limit"]), (3, 1, 1))
        self.assertEqual(body["items"], [{"source": "vk", "kind": "post", "id": "-1_2",
                                          "owner_id": -1, "text": "post 2", "date": 2}])
        for query in ("offset=3", "offset=100", "limit=100"):
            with self.subTest(query=query):
                response = await self.client.get(self.path + "/records?" + query)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["total"], 3)
                self.assertEqual(len(response.json()["items"]), 3 if query == "limit=100" else 0)

    async def test_invalid_pagination(self):
        for query in ("offset=-1", "limit=0", "limit=101", "offset=abc", "limit=1.5"):
            with self.subTest(query=query):
                response = await self.client.get(self.path + "/records?" + query)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")

    async def test_job_isolation(self):
        self.add_posts()
        other = self.store.create()
        response = await self.client.get(f"/collection/{other.collection_id}/records")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)
        self.assertEqual(response.json()["items"], [])


if __name__ == "__main__":
    unittest.main()
