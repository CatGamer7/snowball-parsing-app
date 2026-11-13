# SNO-15 — Model Benchmark

Бенчмарк ML-моделей для модуля `snowball-parsing-app/ml`.

Скрипты измеряют:
- время инференса;
- потребление памяти;
- работу на CPU и GPU;
- входы длиной 128 и 512 токенов.

Методика по умолчанию:
- batch size = 1;
- 3 прогревочных запуска;
- 10 измеряемых запусков;
- загрузка модели в время инференса не входит;
- результаты сохраняются в `results/benchmark_results.csv`;
- ошибки сохраняются в `results/benchmark_errors.log`.

## Структура

```text
ml/benchmark/
├── benchmark_one.py
├── run_all.py
├── check_environment.py
├── models.json
├── requirements.txt
├── METHODOLOGY.md
├── MODELS.md
├── README.md
└── results/
    └── benchmark_results.csv
```

## Модели

| Alias | Model ID | Task |
|---|---|---|
| `e5-small` | `intfloat/multilingual-e5-small` | embeddings |
| `e5-base` | `intfloat/multilingual-e5-base` | embeddings |
| `e5-large` | `intfloat/multilingual-e5-large` | embeddings |
| `minilm` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | embeddings |
| `gte` | `Alibaba-NLP/gte-multilingual-base` | embeddings |
| `bge-m3` | `BAAI/bge-m3` | embeddings |
| `gliner` | `urchade/gliner_multi-v2.1` | NER |
| `spanmarker` | `tomaarsen/span-marker-mbert-base-multinerd` | NER |
| `wikineural` | `Babelscape/wikineural-multilingual-ner` | NER |
| `qwen25` | `Qwen/Qwen2.5-0.5B-Instruct` | keywords |
| `qwen3` | `Qwen/Qwen3-0.6B` | keywords |
| `rut5` | `denis-gordeev/rut5-keyphrase` | keywords |
| `distilbert-kptimes` | `ml6team/keyphrase-extraction-distilbert-kptimes` | keywords |
| `kbir-kptimes` | `ml6team/keyphrase-extraction-kbir-kptimes` | keywords |

## Установка

Из корня репозитория:

```powershell
cd .\ml\benchmark
```

Создать виртуальное окружение:

```powershell
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Обновить pip:

```powershell
python -m pip install --upgrade pip
```

### 1. Установить PyTorch

PyTorch лучше устанавливать отдельно от `requirements.txt`, потому что сборка зависит от железа.

#### AMD Radeon / ROCm на Windows

Для тестового компьютера с AMD Radeon 780M (`gfx1103`) использовались ROCm 10.1 и PyTorch 2.14:

```powershell
python -m pip install --index-url https://stable.repo.amd.com/rocm/whl-next/ "torch[device-gfx1103]==2.14.0+rocm10.1.0" "torchvision[device-gfx1103]==0.29.0a0+rocm10.1.0" "torchaudio==2.11.0.3+rocm10.1.0"
```

В PyTorch ROCm GPU по-прежнему используется через имя устройства `cuda`, поэтому команды бенчмарка используют:

```text
--devices cuda
```

#### CPU / NVIDIA

Для другого оборудования сначала установите подходящую сборку PyTorch:
https://pytorch.org/get-started/locally/

### 2. Установить остальные зависимости

```powershell
python -m pip install -r requirements.txt
```

Проверить совместимость зависимостей:

```powershell
python -m pip check
```

Проверить окружение:

```powershell
python check_environment.py
```

## Полный прогон всех моделей

Запуск всех моделей на всех доступных устройствах:

```powershell
python run_all.py --warmup 3 --runs 10
```

Скрипт последовательно запускает модели в отдельных процессах. Ошибка одной модели не должна останавливать весь набор.

Если в `benchmark_results.csv` уже есть результаты и их нужно сохранить:

```powershell
python run_all.py --warmup 3 --runs 10 --append
```

## Запуск одной модели

Общий формат:

```powershell
python run_all.py --models <alias> --warmup 3 --runs 10 --append
```

Примеры:

```powershell
python run_all.py --models e5-small --warmup 3 --runs 10 --append
python run_all.py --models e5-base --warmup 3 --runs 10 --append
python run_all.py --models e5-large --warmup 3 --runs 10 --append
python run_all.py --models minilm --warmup 3 --runs 10 --append
python run_all.py --models gte --warmup 3 --runs 10 --append
python run_all.py --models bge-m3 --warmup 3 --runs 10 --append
python run_all.py --models gliner --warmup 3 --runs 10 --append
python run_all.py --models spanmarker --warmup 3 --runs 10 --append
python run_all.py --models wikineural --warmup 3 --runs 10 --append
python run_all.py --models qwen25 --warmup 3 --runs 10 --append
python run_all.py --models qwen3 --warmup 3 --runs 10 --append
python run_all.py --models rut5 --warmup 3 --runs 10 --append
python run_all.py --models distilbert-kptimes --warmup 3 --runs 10 --append
python run_all.py --models kbir-kptimes --warmup 3 --runs 10 --append
```

## Запуск только на CPU или GPU

Только CPU:

```powershell
python run_all.py --models gliner --devices cpu --warmup 3 --runs 10 --append
```

Только GPU:

```powershell
python run_all.py --models gliner --devices cuda --warmup 3 --runs 10 --append
```

То же самое работает для любого alias из таблицы выше.

## Быстрый smoke test

Перед полным прогоном можно проверить, что модель вообще запускается:

```powershell
python run_all.py --models gliner --warmup 1 --runs 2 --append
```

После успешного smoke test рекомендуется запускать финальный вариант с `--warmup 3 --runs 10`.

## Результаты

Основной файл:

```text
results/benchmark_results.csv
```

Основные поля:
- `alias` — короткое имя модели;
- `model_id` — ID модели на Hugging Face;
- `task` — тип задачи;
- `device` — CPU или CUDA/ROCm;
- `requested_tokens` — запрошенная длина;
- `effective_tokens` — фактически использованная длина;
- `status` — `ok` или `error`;
- `average_time_ms` — среднее время инференса;
- `min_time_ms` / `max_time_ms` — минимальное и максимальное время;
- `peak_memory_mb` — пиковая память;
- `inference_memory_delta_mb` — прирост памяти во время инференса.

CPU memory измеряется через RSS процесса.

GPU memory измеряется через:

```text
torch.cuda.max_memory_allocated
```

## Ограничения длины

Не все модели реально принимают 512 токенов.

Например:
- `MiniLM` — `effective_tokens = 128`;
- `GLiNER` — `effective_tokens = 384`.

Поэтому в CSV отдельно сохраняются `requested_tokens` и `effective_tokens`.

## Особенности отдельных моделей

### GLiNER + AMD ROCm

На Radeon 780M MIOpen может падать на LSTM с `miopenStatusUnknownError`.

Для AMD ROCm в `benchmark_one.py` используется workaround:

```python
if device == "cuda" and torch.version.hip is not None:
    torch.backends.cudnn.enabled = False
```

Модель при этом остаётся на GPU; отключается проблемный MIOpen/cuDNN RNN fast path.

### GTE multilingual

Для `Alibaba-NLP/gte-multilingual-base` используется:

```python
trust_remote_code=True
```

Рабочая конфигурация бенчмарка использует `transformers==4.57.6`.

### SpanMarker

Для совместимости с используемыми Hugging Face-библиотеками требуется актуальная версия:

```text
span-marker==1.8.1
```

### Qwen

Qwen используется для генерации keywords через фиксированный prompt.

Для сопоставимости замеров:

```text
max_new_tokens = 32
do_sample = False
```

Предупреждения о `temperature`, `top_p` и `top_k` при `do_sample=False` не являются ошибкой и на детерминированный прогон не влияют.

## Рабочие версии ключевых зависимостей

Конфигурация, на которой был выполнен полный прогон:

```text
transformers==4.57.6
sentence-transformers==5.7.0
huggingface_hub==0.36.2
datasets==4.8.5
span-marker==1.8.1
gliner==0.2.30
FlagEmbedding==1.4.2
```

Не рекомендуется выполнять `pip install -U` для Hugging Face-пакетов без проверки совместимости: обновление только одного из `transformers`, `sentence-transformers`, `datasets` или `huggingface_hub` может снова привести к конфликту версий.

## Возможная ошибка proxy

Если Hugging Face падает с ошибкой вида:

```text
Unknown scheme for proxy URL URL('socks4://127.0.0.1:10808')
```

в PowerShell можно очистить proxy-переменные текущей сессии:

```powershell
Remove-Item Env:ALL_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:HTTP_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:HTTPS_PROXY -ErrorAction SilentlyContinue
```

После этого повторить запуск.

## Проверка перед коммитом

```powershell
python -m pip check
python check_environment.py
```

Для проверки одного лёгкого кандидата:

```powershell
python run_all.py --models e5-small --warmup 1 --runs 2 --append
```

Для проверки GLiNER:

```powershell
python run_all.py --models gliner --warmup 1 --runs 2 --append
```
