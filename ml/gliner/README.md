# GLiNER Inference Prototype

Прототип инференса NER-модели `urchade/gliner_multi-v2.1`

Модуль принимает текст и настройки NER через JSON, запускает GLiNER и возвращает найденные сущности в JSON.

## Структура

```text
ml/gliner/
├── gliner_inference.py
├── request.json
├── requirements.txt
└── README.md
```

После запуска также создаётся:

```text
output.json
```

## Требования

- Python 3.10+
- Интернет при первом запуске для загрузки модели с Hugging Face

Модель `urchade/gliner_multi-v2.1` при первом запуске скачивается автоматически. В дальнейшем используется локальный кеш.

## Установка

Перейти в папку модуля:

```bash
cd ml/gliner
```

Создать виртуальное окружение:

```bash
python -m venv .venv
```

### Windows PowerShell

Активировать окружение:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
source .venv/bin/activate
```

Обновить `pip`:

```bash
python -m pip install --upgrade pip
```

Установить зависимости:

```bash
python -m pip install -r requirements.txt
```

## Входные данные

Скрипт получает данные из файла `request.json`.

Пример:

```json
{
  "text": "Иван Петров выступил на форуме компании Яндекс в Москве 15 октября.",
  "models": {
    "urchade/gliner_multi-v2.1": {
      "labels": [
        "person",
        "organization",
        "city",
        "date"
      ],
      "threshold": 0.5
    }
  }
}
```

### Поля

- `text` — текст для обработки.
- `models` — выбранные ML-модели и их параметры.
- `labels` — типы сущностей, которые должен искать GLiNER.
- `threshold` — минимальный confidence score найденной сущности.

Примеры поддерживаемых labels:

```text
person
organization
city
country
date
event
```

## Запуск

```bash
python gliner_inference.py
```

При успешном запуске результат сохраняется в:

```text
output.json
```

## Пример результата

```json
{
  "text": "Иван Петров выступил на форуме компании Яндекс в Москве 15 октября.",
  "results": {
    "urchade/gliner_multi-v2.1": {
      "status": "ok",
      "device": "cpu",
      "fallback": false,
      "output": {
        "labels": [
          "person",
          "organization",
          "city",
          "date"
        ],
        "threshold": 0.5,
        "entities": [
          {
            "text": "Иван Петров",
            "type": "person",
            "start": 0,
            "end": 11,
            "score": 0.98
          },
          {
            "text": "Яндекс",
            "type": "organization",
            "start": 40,
            "end": 46,
            "score": 0.72
          },
          {
            "text": "Москве",
            "type": "city",
            "start": 49,
            "end": 55,
            "score": 0.97
          },
          {
            "text": "15 октября",
            "type": "date",
            "start": 56,
            "end": 66,
            "score": 0.90
          }
        ]
      }
    }
  }
}
```

## GPU / CPU fallback

Если доступен поддерживаемый GPU, скрипт может попытаться использовать его.

Если загрузка модели или инференс на GPU завершается ошибкой, предусмотрен fallback на CPU.

Если GPU недоступен, модель запускается на CPU.

## Ошибки

Ошибки загрузки модели и инференса возвращаются в структурированном виде, чтобы backend мог обработать неуспешный запуск отдельно от успешных результатов других моделей.

## Интеграция с backend

На текущем этапе это файловый прототип инференса:

```text
request.json
    ↓
gliner_inference.py
    ↓
output.json
```

Отдельного HTTP API пока нет.

Для прямого вызова из backend следующим шагом модуль можно обернуть в API, например:

```text
POST /inference
```

с JSON в body запроса и JSON-ответом с найденными сущностями.
