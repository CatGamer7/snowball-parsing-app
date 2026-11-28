"""Сборка автономного Windows-установщика с проверкой реального инференса."""
import argparse
import importlib.util
import json
import os
import platform
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
from urllib.error import URLError
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "packaging"
BUILD_PYTHON = ROOT / "backend/.venv-build/Scripts/python.exe"


def run(command, *, cwd=ROOT, env=None):
    print("\n[BUILD]", subprocess.list2cmdline([str(x) for x in command]), flush=True)
    subprocess.run([str(x) for x in command], cwd=cwd, env=env, check=True)


def npm(*arguments, env=None):
    # Используем npm-cli.js напрямую: без проблем npm.ps1/ExecutionPolicy и shell quoting.
    npm_executable = Path(shutil.which("npm.cmd") or shutil.which("npm") or "")
    node = shutil.which("node")
    candidates = [npm_executable.parent / "node_modules/npm/bin/npm-cli.js"]
    if npm_executable.is_file():
        candidates.append(npm_executable.resolve().parents[1] / "lib/node_modules/npm/bin/npm-cli.js")
    cli = next((path for path in candidates if path.is_file()), None)
    if not node or cli is None:
        raise RuntimeError("Не найден npm-cli.js рядом с npm. Проверьте установку Node.js.")
    run([node, cli, *arguments], cwd=ROOT / "frontend", env=env)


def offline_environment():
    env = os.environ.copy()
    env.update(
        SNOWBALL_MODEL_HUB=str(OUTPUT / "models/hub"),
        SNOWBALL_DEVICE="cpu", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
        PYTHONUTF8="1", PYTHONIOENCODING="utf-8", TOKENIZERS_PARALLELISM="false",
    )
    env.pop("SNOWBALL_MANAGED", None)
    env.pop("SNOWBALL_UI_DIR", None)
    return env


def smoke_backend(executable: Path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = offline_environment()
    instance = str(uuid4())
    env.update(SNOWBALL_PORT=str(port), SNOWBALL_INSTANCE_ID=instance,
               SNOWBALL_MANAGED="1", SNOWBALL_UI_DIR=str(ROOT / "frontend/out/renderer"))
    opener = build_opener(ProxyHandler({}))
    process = subprocess.Popen([str(executable)], stdin=subprocess.PIPE, env=env, cwd=OUTPUT)
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("backend.exe завершился до проверки /health")
            try:
                with opener.open(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                    if response.headers.get("X-Snowball-Instance") == instance and json.load(response)["status"] == "ok":
                        break
            except (URLError, OSError):
                pass
            time.sleep(.2)
        else:
            raise RuntimeError("backend.exe не ответил на /health")
        with opener.open(f"http://127.0.0.1:{port}/app/index.html", timeout=3) as response:
            if b'<div id="root"' not in response.read():
                raise RuntimeError("backend.exe не отдал собранный интерфейс")
    finally:
        if process.poll() is None:
            try:
                process.stdin.write(b"shutdown\n")
                process.stdin.close()
                process.wait(timeout=12)
            except (OSError, subprocess.TimeoutExpired):
                run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"])
        if process.poll() is None:
            raise RuntimeError("Не удалось остановить проверочный backend.exe")
    print("SNOWBALL_HTTP_OK: health, UI, shutdown", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-models", action="store_true", help="брать модель только из имеющегося HF-кэша")
    parser.add_argument("--reuse-env", action="store_true", help="повторно использовать уже подготовленное build-окружение")
    parser.add_argument("--skip-models", action="store_true", help="не пересобирать уже подготовленный пакет весов")
    parser.add_argument("--unpacked", action="store_true", help="собрать win-unpacked вместо NSIS для диагностики")
    args = parser.parse_args()
    if sys.platform != "win32" or struct.calcsize("P") != 8 or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Сборку нужно выполнять на Windows с 64-битным Python.")
    for name in ["gliner", "torch", "transformers", "packaging"]:
        if importlib.util.find_spec(name) is None:
            raise RuntimeError(f"В рабочем backend/.venv отсутствует {name}")
    if not shutil.which("node") or not shutil.which("npm.cmd"):
        raise RuntimeError("Нужны Node.js и npm в PATH.")
    OUTPUT.mkdir(exist_ok=True)
    if not (ROOT / "frontend/node_modules/electron/path.txt").is_file():
        npm("ci")
    frontend_env = os.environ.copy()
    frontend_env["VITE_API_URL"] = "http://127.0.0.1:8000"
    frontend_env["CSC_IDENTITY_AUTO_DISCOVERY"] = "false"
    npm("run", "build", env=frontend_env)
    run([sys.executable, ROOT / "build_tools/collect_versions.py", OUTPUT])
    versions = json.loads((OUTPUT / "runtime-versions.json").read_text(encoding="utf-8"))
    if not args.reuse_env or not BUILD_PYTHON.is_file():
        if BUILD_PYTHON.parent.parent.exists():
            shutil.rmtree(BUILD_PYTHON.parent.parent)
        run([sys.executable, "-m", "venv", BUILD_PYTHON.parent.parent])
        run([BUILD_PYTHON, "-m", "pip", "install", "--upgrade", "pip"])
        torch_version = versions["torch"].split("+")[0]
        run([BUILD_PYTHON, "-m", "pip", "install", "torch==" + torch_version,
             "--index-url", "https://download.pytorch.org/whl/cpu"])
        run([BUILD_PYTHON, "-m", "pip", "install", "-r", OUTPUT / "runtime-requirements.txt"])
        run([BUILD_PYTHON, "-m", "pip", "install", "pyinstaller>=6.11,<7"])
    run([BUILD_PYTHON, "-m", "pip", "check"])
    with (OUTPUT / "build-packages.txt").open("w", encoding="utf-8") as stream:
        subprocess.run([str(BUILD_PYTHON), "-m", "pip", "list", "--format=freeze"], stdout=stream, check=True)
    if not args.skip_models:
        command = [BUILD_PYTHON, ROOT / "build_tools/prepare_models.py", OUTPUT / "models"]
        if args.local_models:
            command.append("--local-only")
        run(command)
    if not (OUTPUT / "models/manifest.json").is_file():
        raise RuntimeError("Сначала нужно подготовить веса без --skip-models.")
    run([BUILD_PYTHON, ROOT / "backend/entrypoint.py", "--self-check"], env=offline_environment())
    run([BUILD_PYTHON, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", OUTPUT / "backend", "--workpath", OUTPUT / "pyinstaller",
         ROOT / "build_tools/backend.spec"])
    executable = OUTPUT / "backend/snowball-backend/snowball-backend.exe"
    if not executable.is_file():
        raise RuntimeError("PyInstaller не создал backend.exe.")
    run([executable, "--self-check"], env=offline_environment())
    smoke_backend(executable)
    # Передаём только сформированные каталоги, не .venv, исходные .env и весь HF-кэш.
    npm("exec", "--", "electron-builder", "--win", "--x64",
        *( ["--dir"] if args.unpacked else [] ), env=frontend_env)
    print("\n[BUILD] Готово. Результат: frontend/dist", flush=True)
    print("Проверьте установку, реальный сбор и завершение процессов на другом Windows-компьютере.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as error:
        print("\n[BUILD FAILED]", error, flush=True)
        raise SystemExit(1)
