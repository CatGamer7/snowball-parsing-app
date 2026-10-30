MODELS = [
    {
        "id": "urchade/gliner_multi-v2.1",
        "name": "GLiNER multi v2.1",
        "description": (
            "Извлечение сущностей с заданными пользователем типами. "
            "Основной вариант."
        ),
        "task": "ner",
        "settings_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["labels"],
            "properties": {
                "labels": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "minLength": 1,
                        "pattern": r"\S",
                    },
                    "description": (
                        "Типы сущностей, например person, organization, city."
                    ),
                }
            },
        },
    },
    {
        "id": "Babelscape/wikineural-multilingual-ner",
        "name": "WikiNEuRal multilingual NER",
        "description": (
            "Дополнительная NER-модель. "
            "В этой версии пользовательские настройки не предусмотрены."
        ),
        "task": "ner",
        "settings_schema": {
            "type": "object",
            "additionalProperties": False,
        },
    },
]