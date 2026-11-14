"""Точка входа backend.exe; родитель Electron управляет жизненным циклом через stdin."""
import argparse
from multiprocessing import freeze_support
import os
import sys
import threading


def main() -> int:
    freeze_support()
    from runtime import configure_packaged_environment
    configure_packaged_environment()
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        os.environ["SNOWBALL_BUILD_CHECK"] = "1"
        # Проверяем настоящую модель и токенизатор без VK и без загрузок из сети.
        from services.ner import ner_extractor
        entities = ner_extractor.extract(
            "Иван Петров выступил в Москве на встрече компании Яндекс.",
            ["person", "organization", "city"], .5,
        )
        print(f"SNOWBALL_ML_OK entities={len(entities)}", flush=True)
        return 0

    import uvicorn
    from main import app
    from config import HOST, PORT
    server = uvicorn.Server(uvicorn.Config(
        app, host=HOST, port=PORT, access_log=False,
        loop="asyncio", http="h11", ws="none", lifespan="on",
        timeout_graceful_shutdown=3,
    ))

    if os.environ.get("SNOWBALL_MANAGED") == "1":
        def watch_parent():
            try:
                while True:
                    line = sys.stdin.buffer.readline()
                    if not line or line.strip() == b"shutdown":
                        break
            finally:
                server.should_exit = True
                # Не оставляем backend при аварии Electron или зависшем ML-потоке.
                timer = threading.Timer(10, lambda: os._exit(0))
                timer.daemon = True
                timer.start()
        threading.Thread(target=watch_parent, daemon=True, name="electron-parent").start()

    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
