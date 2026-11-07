import json
import sys
import gc
from pathlib import Path

import torch
from gliner import GLiNER


MODEL_NAME = "urchade/gliner_multi-v2.1"
DEFAULT_INPUT_FILE = "request.json"
DEFAULT_OUTPUT_FILE = "output.json"

DEFAULT_LABELS = [
    "person",
    "organization",
    "city",
    "country",
    "date",
    "event"
]

DEFAULT_THRESHOLD = 0.5


def read_request(input_path):
    with open(input_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    text = data.get("text")

    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            "Поле 'text' обязательно и должно быть непустой строкой."
        )

    models = data.get("models")

    if not isinstance(models, dict):
        raise ValueError(
            "Поле 'models' обязательно и должно быть JSON-объектом."
        )

    if MODEL_NAME not in models:
        raise ValueError(
            f"Модель '{MODEL_NAME}' не выбрана в поле 'models'."
        )

    settings = models[MODEL_NAME]

    if settings is None:
        settings = {}

    if not isinstance(settings, dict):
        raise ValueError(
            f"Настройки модели '{MODEL_NAME}' должны быть JSON-объектом."
        )

    labels = settings.get("labels", DEFAULT_LABELS)

    if not isinstance(labels, list) or not labels:
        raise ValueError(
            "Поле 'labels' должно быть непустым массивом строк."
        )

    if not all(isinstance(label, str) and label.strip() for label in labels):
        raise ValueError(
            "Каждый элемент 'labels' должен быть непустой строкой."
        )

    threshold = settings.get("threshold", DEFAULT_THRESHOLD)

    if not isinstance(threshold, (int, float)):
        raise ValueError(
            "Поле 'threshold' должно быть числом."
        )

    threshold = float(threshold)

    if not 0.0 <= threshold <= 1.0:
        raise ValueError(
            "Поле 'threshold' должно находиться в диапазоне от 0 до 1."
        )

    return text.strip(), labels, threshold


def save_json(output_path, result):
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )


def load_model(device):
    print(f"Загрузка {MODEL_NAME} на {device}...")

    model = GLiNER.from_pretrained(MODEL_NAME)
    model = model.to(device)

    if hasattr(model, "eval"):
        model.eval()

    return model


def run_inference(model, text, labels, threshold):
    print("Запуск NER-инференса...")

    with torch.inference_mode():
        raw_entities = model.predict_entities(
            text,
            labels,
            threshold=threshold
        )

    entities = []

    for entity in raw_entities:
        entities.append(
            {
                "text": entity.get("text"),
                "type": entity.get("label"),
                "start": entity.get("start"),
                "end": entity.get("end"),
                "score": float(entity.get("score", 0.0))
            }
        )

    return entities


def run_on_device(text, labels, threshold, device):
    model = None

    try:
        model = load_model(device)
        entities = run_inference(
            model,
            text,
            labels,
            threshold
        )
        return entities

    finally:
        if model is not None:
            del model

        gc.collect()

        if device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()


def build_success_response(
    text,
    labels,
    threshold,
    entities,
    device,
    fallback,
    fallback_reason=None
):
    model_result = {
        "status": "ok",
        "device": device,
        "fallback": fallback,
        "output": {
            "labels": labels,
            "threshold": threshold,
            "entities": entities
        }
    }

    if fallback_reason is not None:
        model_result["fallback_reason"] = fallback_reason

    return {
        "text": text,
        "results": {
            MODEL_NAME: model_result
        }
    }


def build_error_response(
    text,
    stage,
    message,
    gpu_error=None,
    cpu_error=None
):
    error = {
        "stage": stage,
        "message": message
    }

    if gpu_error is not None:
        error["gpu_error"] = str(gpu_error)

    if cpu_error is not None:
        error["cpu_error"] = str(cpu_error)

    return {
        "text": text,
        "results": {
            MODEL_NAME: {
                "status": "error",
                "error": error
            }
        }
    }


def main():
    input_path = Path(
        sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT_FILE
    )
    output_path = Path(
        sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT_FILE
    )

    text = ""

    try:
        text, labels, threshold = read_request(input_path)

    except Exception as error:
        result = build_error_response(
            text=text,
            stage="input",
            message=str(error)
        )
        save_json(output_path, result)

        print("Ошибка входных данных:")
        print(error)
        print(f"Информация об ошибке сохранена в {output_path}")
        return 1

    if torch.cuda.is_available():
        print("CUDA доступна.")
        print("GPU:", torch.cuda.get_device_name(0))

        try:
            entities = run_on_device(
                text,
                labels,
                threshold,
                "cuda"
            )

            result = build_success_response(
                text=text,
                labels=labels,
                threshold=threshold,
                entities=entities,
                device="cuda",
                fallback=False
            )

            save_json(output_path, result)

            print("Инференс успешно выполнен на GPU.")
            print("Найдено сущностей:", len(entities))
            print(f"Результат сохранён в {output_path}")
            return 0

        except Exception as gpu_error:
            print("Ошибка загрузки или инференса на GPU:")
            print(gpu_error)
            print("Выполняется fallback на CPU...")

            try:
                entities = run_on_device(
                    text,
                    labels,
                    threshold,
                    "cpu"
                )

                result = build_success_response(
                    text=text,
                    labels=labels,
                    threshold=threshold,
                    entities=entities,
                    device="cpu",
                    fallback=True,
                    fallback_reason=str(gpu_error)
                )

                save_json(output_path, result)

                print("Fallback успешен: инференс выполнен на CPU.")
                print("Найдено сущностей:", len(entities))
                print(f"Результат сохранён в {output_path}")
                return 0

            except Exception as cpu_error:
                result = build_error_response(
                    text=text,
                    stage="load_or_inference",
                    message=(
                        "Не удалось выполнить модель ни на GPU, "
                        "ни после fallback на CPU."
                    ),
                    gpu_error=gpu_error,
                    cpu_error=cpu_error
                )

                save_json(output_path, result)

                print("Ошибка CPU после fallback:")
                print(cpu_error)
                print(f"Информация об ошибке сохранена в {output_path}")
                return 1

    print("CUDA недоступна. Используется CPU.")

    try:
        entities = run_on_device(
            text,
            labels,
            threshold,
            "cpu"
        )

        result = build_success_response(
            text=text,
            labels=labels,
            threshold=threshold,
            entities=entities,
            device="cpu",
            fallback=False
        )

        save_json(output_path, result)

        print("Инференс успешно выполнен на CPU.")
        print("Найдено сущностей:", len(entities))
        print(f"Результат сохранён в {output_path}")
        return 0

    except Exception as error:
        result = build_error_response(
            text=text,
            stage="load_or_inference",
            message=str(error)
        )

        save_json(output_path, result)

        print("Ошибка загрузки модели или инференса:")
        print(error)
        print(f"Информация об ошибке сохранена в {output_path}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
