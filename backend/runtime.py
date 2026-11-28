"""Пути и окружение исходников и установленного приложения."""
import os
from pathlib import Path
import sys


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def ml_module_path() -> Path:
    return resource_root() / "ml/gliner/gliner_inference.py"


def configure_packaged_environment() -> None:
    hub = os.environ.get("SNOWBALL_MODEL_HUB")
    if hub:
        path = Path(hub).resolve()
        if not path.is_dir():
            raise RuntimeError("Не найден каталог встроенной модели")
        os.environ["HF_HUB_CACHE"] = str(path)
        os.environ["HUGGINGFACE_HUB_CACHE"] = str(path)
        os.environ["TRANSFORMERS_CACHE"] = str(path)
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    if getattr(sys, "frozen", False):
        os.environ.setdefault("SNOWBALL_DEVICE", "cpu")
