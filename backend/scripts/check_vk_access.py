"""Live VK access probe before API collection tests; no mocks or ML model."""
import argparse
import asyncio
import getpass
import warnings

import httpx

from core.source import SearchQuery
from vk.client import VKAPIError, VKClient
from vk.source import VKDataSource


async def probe(token: str, group: str, query: str, limit: int) -> int:
    failed = False

    async def check(method, operation):
        nonlocal failed
        try:
            records = await operation()
            print(f"OK {method}: records={len(records)}")
            return records
        except VKAPIError as exc:
            # Do not print VK's message or response: they can contain request data.
            print(f"FAIL {method}: VK error code={exc.code}")
        except httpx.HTTPStatusError as exc:
            print(f"FAIL {method}: HTTP status={exc.response.status_code}")
        except httpx.HTTPError as exc:
            print(f"FAIL {method}: network error ({type(exc).__name__})")
        except (ValueError, KeyError, TypeError):
            print(f"FAIL {method}: unexpected response format")
        failed = True
        return None

    async with VKClient(token) as client:
        source = VKDataSource(client)
        groups = await check("groups.getById", lambda: source.get_by_ids("group", [group]))
        if groups and len(groups) == 1:
            await check("wall.get", lambda: source.get_wall_posts(-int(groups[0].id), limit=limit))
        else:
            failed = True
            print("SKIP wall.get: could not resolve exactly one starting group")

        await check("newsfeed.search", lambda: source.search(SearchQuery(
            source="vk", kind="post", text=query, limit=limit,
        )))
        print(f"VK requests: {client.requests_count}")

    print("RESULT: access checks failed or were blocked" if failed else "RESULT: access checks passed")
    print("Zero records means the request succeeded but returned no posts; ML was not tested.")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="vk", help="Public group ID or short name (default: vk)")
    parser.add_argument("--query", default="ТПУ", help="Post search query (default: ТПУ)")
    parser.add_argument("--limit", type=int, choices=range(1, 6), default=3)
    args = parser.parse_args()
    if not args.group.strip() or not args.query.strip():
        parser.error("group and query must not be blank")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("VK service key (hidden input): ").strip()
    except (getpass.GetPassWarning, EOFError):
        print("Cannot read the key securely. Run this command in an interactive terminal.")
        return 2
    if not token:
        print("No key entered.")
        return 2
    return asyncio.run(probe(token, args.group.strip(), args.query.strip(), args.limit))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
