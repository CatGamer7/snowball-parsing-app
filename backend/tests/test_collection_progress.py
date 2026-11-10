import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from main import app
from core.jobs import CollectionFailure, CollectionJobStore
from core.models import Record


class JobStoreTests(unittest.TestCase):
    def test_lifecycle_and_utc_dates(self):
        store = CollectionJobStore()
        job = store.create(vk_requests_count=3)
        self.assertEqual(job.status, 'queued')
        self.assertIsNone(job.started_at)
        store.start(job.collection_id)
        store.update_counts(job.collection_id, records_count=12, expansion_level=1,
                            selected_entities_count=5, vk_requests_count=9)
        store.finish(job.collection_id)
        result = store.get(job.collection_id)
        self.assertEqual(result.status, 'completed')
        self.assertEqual(result.records_count, 12)
        self.assertEqual(result.vk_requests_count, 9)
        self.assertIsNotNone(result.started_at.tzinfo)
        self.assertGreaterEqual(result.finished_at, result.started_at)
        self.assertIsNone(result.error)
        with self.assertRaises(ValueError):
            store.start(job.collection_id)

    def test_failure_preserves_counts(self):
        store = CollectionJobStore()
        job = store.create(vk_requests_count=2)
        store.start(job.collection_id)
        store.finish(job.collection_id, CollectionFailure(code='ML_ERROR', message='Ошибка модели'))
        result = store.get(job.collection_id)
        self.assertEqual(result.status, 'failed')
        self.assertEqual(result.error.code, 'ML_ERROR')
        self.assertEqual(result.vk_requests_count, 2)
        self.assertIsNone(store.get('unknown'))

    def test_jobs_are_independent_and_snapshots_detached(self):
        store = CollectionJobStore()
        first, second = store.create(), store.create()
        snapshot = store.get(first.collection_id)
        snapshot.__dict__['records_count'] = 999
        self.assertEqual(store.get(first.collection_id).records_count, 0)
        store.start(first.collection_id)
        self.assertEqual(store.get(second.collection_id).status, 'queued')
        with self.assertRaises(ValueError):
            store.update_counts(first.collection_id, records_count=-1, expansion_level=0,
                                selected_entities_count=0, vk_requests_count=0)


class FakeVKClient:
    def __init__(self, token):
        self.requests_count = 3
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass


class ProgressAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_unknown_job(self):
        response = self.client.get('/collection/missing/progress')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()['error']['code'], 'COLLECTION_NOT_FOUND')

    def test_start_and_actual_failed_progress_without_network(self):
        records = [Record(source='vk', kind='group', id='1'),
                   Record(source='vk', kind='post', id='-1_1')]
        body = {'token': 'test-only-token', 'seeds': [{'type':'group', 'id':'vk'}],
                'rules': {'models': {'Babelscape/wikineural-multilingual-ner': {}},
                          'threshold': .5, 'max_depth': 2}}
        with patch('api.collection_routes.VKClient', FakeVKClient), \
             patch('api.collection_routes.detect_token', new_callable=AsyncMock), \
             patch('api.collection_routes.load_seeds', new_callable=AsyncMock, return_value=records):
            response = self.client.post('/collection/start', json=body)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['status'], 'running')
        result = self.client.get('/collection/'+response.json()['collection_id']+'/progress')
        self.assertEqual(result.status_code, 200)
        progress = result.json()
        self.assertEqual(progress['status'], 'failed')
        self.assertEqual(progress['error']['code'], 'ML_NOT_AVAILABLE')
        self.assertEqual(progress['records_count'], 1)
        self.assertEqual(progress['vk_requests_count'], 3)
        self.assertEqual(progress['expansion_level'], 0)
        self.assertEqual(progress['selected_entities_count'], 0)
        self.assertIsNotNone(progress['started_at'])
        self.assertIsNotNone(progress['finished_at'])
        self.assertNotIn('test-only-token', result.text)

    def test_validation_and_cors(self):
        response = self.client.post('/collection/start', json={},
                                    headers={'Origin':'http://127.0.0.1:5173'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['error']['code'], 'VALIDATION_ERROR')
        self.assertEqual(response.headers['access-control-allow-origin'], 'http://127.0.0.1:5173')

    def test_background_unexpected_error_is_recorded(self):
        from api.collection_routes import run_collection, job_store
        import asyncio
        job = job_store.create()
        with patch.object(job_store, 'update_counts', side_effect=RuntimeError('test')):
            asyncio.run(run_collection(job.collection_id, [], 0))
        progress = job_store.get(job.collection_id)
        self.assertEqual(progress.status, 'failed')
        self.assertEqual(progress.error.code, 'INTERNAL_ERROR')


if __name__ == '__main__':
    unittest.main()
