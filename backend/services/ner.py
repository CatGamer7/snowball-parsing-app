"""Прямой вызов прототипа SNO-14 без временных request/output JSON."""
import importlib.util
import logging
import os
from threading import Lock

from runtime import configure_packaged_environment, ml_module_path


GLINER_ID = "urchade/gliner_multi-v2.1"
logger = logging.getLogger("snowball.ml")


class MLNotAvailable(Exception):
    pass


class MLInferenceError(Exception):
    pass


class GLiNERExtractor:
    """Один экземпляр модели; загрузка и инференс выполняются под блокировкой."""

    def __init__(self):
        self._lock = Lock()
        self._module = None
        self._model = None
        self._device = "cpu"

    @staticmethod
    def validate_models(models: dict) -> None:
        if set(models) != {GLINER_ID}:
            raise MLNotAvailable(
                "В этом сборщике подключён только GLiNER. "
                "Выберите только urchade/gliner_multi-v2.1."
            )

    def _load_module(self):
        if self._module is not None:
            return
        configure_packaged_environment()
        path = ml_module_path()
        if not path.is_file():
            raise MLNotAvailable("Не найден ml/gliner/gliner_inference.py из ветки SNO-14.")
        spec = importlib.util.spec_from_file_location("snowball_sno14_gliner", path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except ImportError:
            if os.environ.get("SNOWBALL_BUILD_CHECK") == "1":
                raise
            raise MLNotAvailable(
                "Не удалось импортировать ML-модуль. "
                "Проверьте зависимости ml/gliner/requirements.txt в окружении бэкенда."
            ) from None
        self._module = module

    def _load_model(self):
        if self._model is not None:
            return
        module = self._module
        self._device = (
            "cuda" if os.environ.get("SNOWBALL_DEVICE") != "cpu"
            and module.torch.cuda.is_available() else "cpu"
        )
        try:
            self._model = module.load_model(self._device)
        except Exception:
            if self._device != "cuda":
                raise
            logger.warning("Загрузка GLiNER на GPU не удалась; используется CPU")
            self._device = "cpu"
            module.torch.cuda.empty_cache()
            self._model = module.load_model("cpu")

    def extract(self, text: str, labels: list[str], threshold: float) -> list[dict]:
        # Вызывается через asyncio.to_thread: event loop продолжает обслуживать API.
        with self._lock:
            try:
                self._load_module()
                self._load_model()
                try:
                    return self._module.run_inference(self._model, text, labels, threshold)
                except Exception:
                    if self._device != "cuda":
                        raise
                    logger.warning("Инференс GLiNER на GPU не удался; используется CPU")
                    self._model = None
                    self._device = "cpu"
                    self._module.torch.cuda.empty_cache()
                    self._model = self._module.load_model("cpu")
                    return self._module.run_inference(self._model, text, labels, threshold)
            except MLNotAvailable:
                raise
            except Exception as exc:
                if os.environ.get("SNOWBALL_BUILD_CHECK") == "1":
                    raise
                # Не отдаём клиенту текст поста, локальные пути или детали библиотек.
                logger.error("Ошибка GLiNER | %s", type(exc).__name__)
                raise MLInferenceError(
                    "Ошибка загрузки или выполнения GLiNER. Проверьте запуск ML-модуля отдельно."
                ) from None


ner_extractor = GLiNERExtractor()
