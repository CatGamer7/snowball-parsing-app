"""Запуск исходников SnowBall: backend + Electron, без сторонних Python-пакетов."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
API_PORT = 8000
UI_PORT = 5173


class LaunchError(Exception):
    pass


def say(message: str) -> None:
    print(f"[SnowBall] {message}", flush=True)


def require_free_port(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(.5)
        # Проверяем слушающий сервер, а не TIME_WAIT после предыдущего запуска.
        if probe.connect_ex((HOST, port)) == 0:
            raise LaunchError(
                f"Порт {port} занят. Остановите ранее запущенный backend или frontend "
                "и повторите запуск. Чужой процесс не будет остановлен автоматически."
            )


def preflight(root: Path) -> tuple[str, list[str]]:
    python = root / "backend/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        raise LaunchError(f"Не найден Python бэкенда: {python}")
    required = ["backend/main.py", "ml/gliner/gliner_inference.py",
                "frontend/package.json"]
    for name in required:
        if not (root / name).is_file():
            raise LaunchError(f"Не найден файл проекта: {name}")
    node = shutil.which("node")
    if node is None:
        raise LaunchError("Не найден Node.js в PATH. Установите Node.js и переоткройте терминал.")
    npm = shutil.which("npm")
    if npm is None:
        raise LaunchError("Не найден npm в PATH. Проверьте установку Node.js.")
    try:
        package = json.loads((root / "frontend/package.json").read_text(encoding="utf-8-sig"))
        if not package.get("scripts", {}).get("dev"):
            raise LaunchError("В frontend/package.json не найдена команда dev. Уточните команду у разработчика фронтенда.")
    except (ValueError, AttributeError):
        raise LaunchError("Не удалось прочитать команды frontend/package.json.") from None
    if os.name == "nt":
        shell = shutil.which("cmd.exe")
        if shell is None:
            raise LaunchError("Не найден cmd.exe для запуска существующей команды npm.")
        frontend_command = [shell, "/d", "/s", "/c", "npm run dev"]
    else:
        frontend_command = [npm, "run", "dev"]
    for name in ["electron-vite/package.json", "electron/path.txt"]:
        if not (root / "frontend/node_modules" / name).is_file():
            raise LaunchError(
                "Не установлены зависимости фронтенда. Из корня проекта выполните: "
                "npm --prefix frontend ci"
            )
    check = (
        "import importlib.util, json; "
        "names=['fastapi','uvicorn','pydantic','httpx','torch','gliner','sentencepiece']; "
        "print(json.dumps([n for n in names if importlib.util.find_spec(n) is None]))"
    )
    try:
        result = subprocess.run(
            [str(python), "-c", check], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        if result.returncode:
            raise LaunchError("Не удалось проверить Python-окружение бэкенда.")
        missing = json.loads(result.stdout)
        if missing:
            raise LaunchError(
                "В окружении бэкенда отсутствуют: " + ", ".join(missing)
                + ". Установите backend/requirements.txt и ml/gliner/requirements.txt."
            )
        version = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=10,
        )
        if version.returncode:
            raise LaunchError("Node.js найден, но не запускается.")
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        raise LaunchError("Ошибка проверки окружения: " + type(exc).__name__) from None
    say(f"Python: {python}")
    say(f"Node.js: {version.stdout.strip()}")
    return str(python), frontend_command


class WindowsJob:
    """Job Object завершает только запущенные нами дочерние процессы и их потомков."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IOCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IOCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self.ctypes = ctypes
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                       ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise LaunchError("Не удалось создать группу процессов Windows.")
        info = ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise LaunchError("Не удалось настроить остановку процессов Windows.")

    def assign(self, process: subprocess.Popen) -> None:
        handle = self.kernel.OpenProcess(0x0100 | 0x0001, False, process.pid)
        if not handle:
            raise LaunchError("Не удалось получить управление дочерним процессом.")
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, handle):
                raise LaunchError("Не удалось включить процесс в группу Windows.")
        finally:
            self.kernel.CloseHandle(handle)

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def child_main() -> int:
    # Барьер: supervisor сначала назначает Job Object и лишь затем передаёт команду.
    # Поэтому Electron не успевает создать потомков вне управляемой группы Windows.
    line = sys.stdin.buffer.readline()
    if not line:
        return 1
    command = json.loads(line.decode("utf-8"))
    # На Linux exec сохраняет группу процессов; в Windows потомки наследуют Job Object.
    if os.name == "nt":
        # Windows exec создаёт другой процесс; bootstrap остаётся и ждёт его код.
        try:
            return subprocess.call(command)
        except KeyboardInterrupt:
            return 130
    os.execv(command[0], command)
    return 1


class ProcessGroup:
    def __init__(self, python: str, bootstrap: Path):
        self.python = python
        self.bootstrap = bootstrap
        self.job = WindowsJob() if os.name == "nt" else None
        self.children: list[subprocess.Popen] = []

    def start(self, command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        process = subprocess.Popen(
            [self.python, "-u", str(self.bootstrap), "--child"],
            cwd=cwd, env=env, stdin=subprocess.PIPE, **options,
        )
        self.children.append(process)
        try:
            if self.job:
                self.job.assign(process)
            process.stdin.write((json.dumps(command, ensure_ascii=False) + "\n").encode("utf-8"))
            process.stdin.close()
        except BaseException:
            # До открытия барьера дочерний процесс ещё не запустил приложение.
            if process.poll() is None:
                process.kill()
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            raise
        return process

    def close(self) -> None:
        for process in reversed(self.children):
            if process.poll() is None:
                try:
                    if os.name == "nt":
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        os.killpg(process.pid, signal.SIGTERM)
                except (OSError, ProcessLookupError):
                    pass
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and any(p.poll() is None for p in self.children):
            time.sleep(.05)
        if self.job:
            self.job.close()  # Включая потомков уже завершившегося родителя.
        else:
            for process in self.children:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
        for process in self.children:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def wait_http(url: str, process: subprocess.Popen, stop: threading.Event,
              *, health: bool, timeout: float = 60, other: subprocess.Popen | None = None) -> None:
    opener = build_opener(ProxyHandler({}))  # Локальные запросы не отправляем через HTTP-прокси.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if stop.is_set():
            raise InterruptedError
        for current in [process, other]:
            if current is not None and current.poll() is not None:
                raise LaunchError(f"Процесс завершился до готовности приложения (код {current.returncode}).")
        try:
            with opener.open(url, timeout=1) as response:
                if response.status == 200:
                    if not health or json.loads(response.read(4096)).get("status") == "ok":
                        return
        except (URLError, OSError, ValueError, AttributeError):
            pass
        stop.wait(.2)
    raise LaunchError(f"Не дождались готовности {url}. Причина может быть в выводе процесса выше.")


def run_pair(root: Path, python: str, frontend_command: list[str], stop: threading.Event) -> int:
    require_free_port(API_PORT)
    require_free_port(UI_PORT)
    env = os.environ.copy()
    env.update(SNOWBALL_PORT=str(API_PORT), VITE_API_URL=f"http://{HOST}:{API_PORT}",
               PYTHONUNBUFFERED="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env.pop("ELECTRON_RUN_AS_NODE", None)
    group = ProcessGroup(python, Path(__file__).resolve())
    try:
        say("Запускаю backend...")
        backend = group.start([python, "-u", str(root / "backend/main.py")], root / "backend", env)
        wait_http(f"http://{HOST}:{API_PORT}/health", backend, stop, health=True)
        say("Backend готов. Запускаю Electron...")
        frontend = group.start(frontend_command, root / "frontend", env)
        wait_http(f"http://{HOST}:{UI_PORT}", frontend, stop, health=False, other=backend)
        say("Приложение запущено. Swagger: http://127.0.0.1:8000/docs")
        say("Для остановки закройте окно приложения или нажмите Ctrl+C в этом терминале.")
        while not stop.wait(.2):
            if backend.poll() is not None:
                raise LaunchError(f"Backend неожиданно завершился (код {backend.returncode}).")
            if frontend.poll() is not None:
                if frontend.returncode:
                    raise LaunchError(f"Frontend завершился с ошибкой (код {frontend.returncode}).")
                return 0
        return 0
    except InterruptedError:
        return 0
    finally:
        say("Останавливаю процессы демонстрации...")
        group.close()
        say("Процессы демонстрации остановлены.")


def main() -> int:
    if sys.argv[1:] == ["--child"]:
        return child_main()
    parser = argparse.ArgumentParser(description="SnowBall: backend + Electron одной командой")
    parser.add_argument("--check", action="store_true", help="только проверить окружение и порты")
    args = parser.parse_args()
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *args: stop.set())
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda *args: stop.set())
    try:
        python, frontend_command = preflight(ROOT)
        if args.check:
            require_free_port(API_PORT)
            require_free_port(UI_PORT)
            say("Окружение и порты готовы. Для запуска: .\\start-demo.cmd")
            return 0
        return run_pair(ROOT, python, frontend_command, stop)
    except LaunchError as exc:
        say(str(exc))
        return 1
    except OSError as exc:
        say("Ошибка запуска: " + str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
