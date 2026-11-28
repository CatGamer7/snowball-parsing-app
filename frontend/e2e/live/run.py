"""Interactive live UI launcher. Never writes the VK key or browser reports."""
import argparse
import asyncio
from functools import partial
import getpass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Thread
from urllib.request import ProxyHandler, build_opener
import warnings


FRONTEND = Path(__file__).resolve().parents[2]
ROOT = FRONTEND.parent


class LiveFailure(Exception):
    pass


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


async def select_post(token, group):
    sys.path.insert(0, str(ROOT / "backend"))
    import httpx
    from vk.client import VKAPIError, VKClient
    from vk.source import VKDataSource

    try:
        async with VKClient(token) as client:
            source = VKDataSource(client)
            groups = await source.get_by_ids("group", [group])
            if len(groups) != 1:
                raise LiveFailure("Starting public group was not found")
            posts = await source.get_wall_posts(-int(groups[0].id), limit=5)
            post = next((item for item in posts if item.text.strip()), None)
            if post is None:
                raise LiveFailure("No text post found among the latest five; choose another --group")
            # Проверяем доступность чтения отдельного поста до открытия интерфейса.
            found = await source.get_by_ids("post", [post.id])
            if len(found) != 1 or not found[0].text.strip():
                raise LiveFailure("Selected post cannot be read by ID")
            return post.id
    except VKAPIError as exc:
        raise LiveFailure(f"VK preflight failed: code={exc.code}") from None
    except httpx.HTTPError:
        raise LiveFailure("VK preflight network request failed") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", default="vk")
    args = parser.parse_args()
    if not args.group.strip():
        parser.error("group must not be blank")
    output = FRONTEND / "out/renderer"
    if not (output / "index.html").is_file():
        raise LiveFailure("Build the frontend before running the live scenario")
    node = os.environ.get("SNOWBALL_E2E_NODE") or shutil.which("node")
    if not node:
        raise LiveFailure("Node.js was not found")
    try:
        with build_opener(ProxyHandler({})).open("http://127.0.0.1:8000/health", timeout=5) as response:
            if response.status != 200 or json.loads(response.read()).get("status") != "ok":
                raise LiveFailure("Unexpected backend health response")
    except OSError:
        raise LiveFailure("Start backend/.venv/Scripts/python.exe main.py in the first terminal") from None

    try:
        server = ThreadingHTTPServer(("127.0.0.1", 5173), partial(QuietHandler, directory=str(output)))
    except OSError:
        raise LiveFailure("Port 5173 is occupied; close the other frontend and retry") from None
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            token = getpass.getpass("VK service key (hidden input): ").strip()
        if not token or any(char.isspace() for char in token):
            raise LiveFailure("Enter a nonempty single-line key")
        post_id = asyncio.run(select_post(token, args.group.strip()))
        print(f"Preflight passed. Seed post: {post_id}", flush=True)
        print("Running real Electron UI; collection wait limit is 5 minutes.", flush=True)
        env = dict(os.environ)
        env.pop("DEBUG", None)
        env.pop("PWDEBUG", None)
        env.update(SNOWBALL_E2E_TOKEN=token, SNOWBALL_E2E_SEED_POST=post_id,
                   SNOWBALL_E2E_RENDERER_URL="http://127.0.0.1:5173")
        process = subprocess.Popen(
            [node, str(FRONTEND / "e2e/live/scenario.mjs")], cwd=FRONTEND,
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        env.pop("SNOWBALL_E2E_TOKEN", None)
        try:
            for line in process.stdout:
                print(line.rstrip().replace(token, "[TOKEN]"), flush=True)
            return process.wait()
        except KeyboardInterrupt:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
            raise
        finally:
            process.stdout.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (getpass.GetPassWarning, EOFError):
        print("FAIL: cannot read the key securely; use an interactive terminal")
        raise SystemExit(1) from None
    except LiveFailure as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as exc:
        # Never dump a traceback containing a request or credentials.
        print(f"FAIL: live launcher error ({type(exc).__name__})")
        raise SystemExit(1) from None
