"""Ограниченный цикл снежного кома для демонстрационного приложения."""
import asyncio
import logging
import math
import random
import unicodedata
from collections import Counter

import httpx

from api.schemas import StartRequest
from core.jobs import CollectionFailure, CollectionJobStore, job_store
from core.models import Record
from core.source import SearchQuery
from services.ner import GLINER_ID, MLInferenceError, MLNotAvailable, ner_extractor
from vk.client import VKAPIError, VKClient
from vk.models import VKPost
from vk.source import VKDataSource


logger = logging.getLogger("snowball.collection")
POSTS_PER_WALL = 100
POSTS_PER_QUERY = 20
MAX_RECORDS = 5000
MAX_TEXT_CHARS = 4000
MAX_ENTITY_CHARS = 100


def normalize_entity(text: str) -> tuple[str, str]:
    query = " ".join(unicodedata.normalize("NFKC", text).split())
    return query.casefold(), query


def select_entities(
    outputs: list[list[dict]], used: set[str], threshold: float, limit: int,
) -> list[tuple[str, str]]:
    """Частота = число постов, содержащих сущность, а не число её повторов."""
    counts: Counter = Counter()
    spellings: dict[str, str] = {}
    for entities in outputs:
        in_post: set[str] = set()
        if not isinstance(entities, list):
            raise MLInferenceError("ML-модуль вернул неожиданный формат сущностей.")
        for entity in entities:
            if not isinstance(entity, dict):
                raise MLInferenceError("ML-модуль вернул некорректную сущность.")
            text, score = entity.get("text"), entity.get("score")
            if not isinstance(text, str) or not isinstance(score, (int, float)):
                raise MLInferenceError("ML-модуль вернул некорректные поля сущности.")
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise MLInferenceError("ML-модуль вернул некорректный score сущности.")
            key, query = normalize_entity(text)
            if score < threshold or not key or len(query) > MAX_ENTITY_CHARS or key in used:
                continue
            spellings.setdefault(key, query)
            in_post.add(key)
        counts.update(in_post)
    ranked = sorted(counts, key=lambda key: (-counts[key], key))[:limit]
    return [(key, spellings[key]) for key in ranked]


async def run_collection(
    collection_id: str,
    seeds: list[Record],
    initial_vk_requests: int,
    request: StartRequest,
    *,
    store: CollectionJobStore | None = None,
    client_factory=None,
    extractor=None,
) -> None:
    """Состояние и результаты живут в одном процессе до его перезапуска."""
    store = store if store is not None else job_store
    client_factory = client_factory if client_factory is not None else VKClient
    extractor = extractor if extractor is not None else ner_extractor
    client = None
    level = selected = 0
    store.start(collection_id)

    def update():
        current = store.get(collection_id)
        store.update_counts(
            collection_id,
            records_count=current.records_count,
            expansion_level=level,
            selected_entities_count=selected,
            vk_requests_count=initial_vk_requests + (client.requests_count if client else 0),
        )

    def add(posts):
        # Store дополнительно исключает пустые тексты и дубли по ключу записи.
        store.add_records(collection_id, posts, limit=MAX_RECORDS)

    def at_limit():
        return store.get(collection_id).records_count >= MAX_RECORDS

    try:
        update()
        async with client_factory(request.token.get_secret_value()) as client:
            source = VKDataSource(client)
            add([record for record in seeds if isinstance(record, VKPost)])
            update()
            for seed in seeds:
                if at_limit():
                    break
                if seed.kind in {"group", "user"}:
                    owner_id = int(seed.id) * (-1 if seed.kind == "group" else 1)
                    try:
                        posts = await source.get_wall_posts(owner_id, limit=POSTS_PER_WALL)
                        add(posts)
                    finally:
                        update()

            if at_limit():
                store.finish(collection_id, stop_reason="record_limit")
                return
            if store.get(collection_id).records_count == 0:
                store.finish(collection_id, stop_reason="no_text_records")
                return

            extractor.validate_models(request.rules.models)
            labels = request.rules.models[GLINER_ID]["labels"]
            cache: dict[str, list[dict]] = {}
            used_queries: set[str] = set()
            rng = random.Random(0)

            for _ in range(request.rules.max_depth):
                all_posts = store.get_records(collection_id, offset=0, limit=MAX_RECORDS)[1]
                sample = (
                    rng.sample(all_posts, request.rules.sample_size)
                    if len(all_posts) > request.rules.sample_size else all_posts
                )
                outputs = []
                for post in sample:
                    if post.key not in cache:
                        cache[post.key] = await asyncio.to_thread(
                            extractor.extract, post.text[:MAX_TEXT_CHARS],
                            labels, request.rules.threshold,
                        )
                    outputs.append(cache[post.key])
                queries = select_entities(
                    outputs, used_queries, request.rules.threshold, request.rules.top_entities,
                )
                selected = len(queries)
                update()
                if not queries:
                    store.finish(collection_id, stop_reason="no_new_entities")
                    return

                before = store.get(collection_id).records_count
                for key, query in queries:
                    used_queries.add(key)
                    try:
                        posts = await source.search(SearchQuery(
                            source="vk", kind="post", text=query, limit=POSTS_PER_QUERY,
                        ))
                        add(posts)
                    finally:
                        update()
                    if at_limit():
                        break
                level += 1  # Уровень = число выполненных раундов расширения.
                update()
                if at_limit():
                    store.finish(collection_id, stop_reason="record_limit")
                    return
                if store.get(collection_id).records_count == before:
                    store.finish(collection_id, stop_reason="no_new_records")
                    return
            store.finish(collection_id, stop_reason="max_depth")

    except MLNotAvailable as exc:
        update()
        store.finish(collection_id, CollectionFailure(code="ML_NOT_AVAILABLE", message=str(exc)))
    except MLInferenceError as exc:
        update()
        store.finish(collection_id, CollectionFailure(code="ML_ERROR", message=str(exc)))
    except (VKAPIError, httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        update()
        code = f" Код VK: {exc.code}." if isinstance(exc, VKAPIError) else ""
        store.finish(collection_id, CollectionFailure(
            code="VK_ERROR", message="Не удалось получить данные из VK API." + code,
        ))
        logger.warning("Задание %s: ошибка VK | %s", collection_id, type(exc).__name__)
    except Exception as exc:
        # Не позволяем вторичной ошибке обновления скрыть исходный сбой задания.
        try:
            update()
        except Exception:
            pass
        store.finish(collection_id, CollectionFailure(
            code="INTERNAL_ERROR", message="Внутренняя ошибка фонового задания",
        ))
        logger.error("Ошибка задания %s | %s", collection_id, type(exc).__name__)
