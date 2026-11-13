import argparse
import csv
import gc
import json
import os
import threading
import time
import traceback
from pathlib import Path

import psutil
import torch


ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

REGISTRY = json.loads(
    (ROOT / "models.json").read_text(encoding="utf-8")
)

LENGTHS = [128, 512]

RU_TEXT = (
    "Иван Петров рассказал о развитии общественного транспорта в Москве. "
    "Компания Яндекс представила новый городской сервис 15 октября. "
    "Социологи обсуждают общественное мнение, образование, работу, миграцию, "
    "городскую среду и поведение пользователей социальных сетей. "
)

EN_TEXT = (
    "Residents discussed public transport, housing, education, employment "
    "and urban development. Researchers analyzed public opinion, social media "
    "behavior and information distribution. The city council presented a new "
    "transport project on October 15. "
)

GLINER_LABELS = [
    "person",
    "organization",
    "city",
    "country",
    "date",
    "event",
]

GEN_MAX_NEW_TOKENS = 32


def args_parse():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        required=True,
        choices=REGISTRY.keys(),
    )

    parser.add_argument(
        "--device",
        required=True,
        choices=["cpu", "cuda"],
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--output",
        default=str(
            RESULTS_DIR / "benchmark_results.csv"
        ),
    )

    return parser.parse_args()


FIELDS = [
    "alias",
    "model_id",
    "task",
    "device",
    "requested_tokens",
    "effective_tokens",
    "status",
    "average_time_ms",
    "min_time_ms",
    "max_time_ms",
    "peak_memory_mb",
    "inference_memory_delta_mb",
    "memory_metric",
    "warmup_runs",
    "measured_runs",
    "note",
    "error",
]


def append_row(path, row):
    path = Path(path)

    exists = path.exists()

    with path.open(
        "a",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDS,
        )

        if not exists:
            writer.writeheader()

        writer.writerow(
            {
                key: row.get(key, "")
                for key in FIELDS
            }
        )


def base_row(args, meta, requested):
    return {
        "alias": args.model,
        "model_id": meta["model_id"],
        "task": meta["task"],
        "device": args.device.upper(),
        "requested_tokens": requested,
        "effective_tokens": min(
            requested,
            meta["max_input_tokens"],
        ),
        "warmup_runs": args.warmup,
        "measured_runs": args.runs,
        "note": meta["notes"],
    }


def long_text(lang):
    text = RU_TEXT if lang == "ru" else EN_TEXT
    return (text + " ") * 400


def cpu_monitor_start():
    process = psutil.Process(os.getpid())

    baseline = process.memory_info().rss
    peak = [baseline]

    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                current = process.memory_info().rss
                peak[0] = max(
                    peak[0],
                    current,
                )
            except psutil.Error:
                pass

            time.sleep(0.002)

    thread = threading.Thread(
        target=worker,
        daemon=True,
    )

    thread.start()

    return baseline, peak, stop, thread


def timed(
    run_once,
    device,
    warmup,
    runs,
):
    # Прогрев
    for _ in range(warmup):
        run_once()

    times = []

    if device == "cuda":
        torch.cuda.synchronize()

        baseline = torch.cuda.memory_allocated()

        torch.cuda.reset_peak_memory_stats()

        for _ in range(runs):
            torch.cuda.synchronize()

            start = time.perf_counter()

            run_once()

            torch.cuda.synchronize()

            elapsed = (
                time.perf_counter() - start
            ) * 1000

            times.append(elapsed)

        peak = torch.cuda.max_memory_allocated()

        peak_mb = peak / (1024 ** 2)

        delta = max(
            0,
            peak - baseline,
        ) / (1024 ** 2)

        metric = (
            "torch.cuda.max_memory_allocated"
        )

    else:
        (
            baseline,
            peak,
            stop,
            thread,
        ) = cpu_monitor_start()

        for _ in range(runs):
            start = time.perf_counter()

            run_once()

            elapsed = (
                time.perf_counter() - start
            ) * 1000

            times.append(elapsed)

        stop.set()
        thread.join()

        peak_mb = peak[0] / (1024 ** 2)

        delta = max(
            0,
            peak[0] - baseline,
        ) / (1024 ** 2)

        metric = "process RSS"

    return (
        sum(times) / len(times),
        min(times),
        max(times),
        peak_mb,
        delta,
        metric,
    )


def fixed_batch(
    tokenizer,
    text,
    n,
    prefix="",
):
    return tokenizer(
        prefix + text,
        return_tensors="pt",
        truncation=True,
        max_length=n,
        padding="max_length",
    )


def load_adapter(meta, device):
    model_id = meta["model_id"]
    kind = meta["loader"]

    text = long_text(
        meta["language"]
    )

    # ==========================================================
    # Sentence Transformers
    # ==========================================================

    if kind in (
        "sentence_transformer",
        "sentence_transformer_gte",
    ):
        from sentence_transformers import (
            SentenceTransformer,
        )

        kwargs = {}

        if kind == "sentence_transformer_gte":
            kwargs["trust_remote_code"] = True

        model = SentenceTransformer(
            model_id,
            device=device,
            **kwargs,
        )

        tokenizer = model.tokenizer

        def builder(n):
            old_max_seq_length = (
                model.max_seq_length
            )

            model.max_seq_length = n

            prepared = (
                meta.get("prefix", "")
                + text
            )

            def run():
                with torch.inference_mode():
                    model.encode(
                        prepared,
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    )

            def cleanup():
                model.max_seq_length = (
                    old_max_seq_length
                )

            return run, cleanup

        return (
            model,
            tokenizer,
            builder,
        )

    # ==========================================================
    # BGE-M3
    # ==========================================================

    if kind == "bge_m3":
        from FlagEmbedding import (
            BGEM3FlagModel,
        )

        from transformers import (
            AutoTokenizer,
        )

        model = BGEM3FlagModel(
            model_id,
            use_fp16=(device == "cuda"),
            device=device,
        )

        tokenizer = (
            AutoTokenizer.from_pretrained(
                model_id
            )
        )

        def builder(n):
            def run():
                model.encode(
                    [text],
                    batch_size=1,
                    max_length=n,
                    return_dense=True,
                    return_sparse=False,
                    return_colbert_vecs=False,
                )

            return run, lambda: None

        return (
            model,
            tokenizer,
            builder,
        )

    # ==========================================================
    # GLiNER
    # ==========================================================

    if kind == "gliner":
        from gliner import GLiNER

        from transformers import (
            AutoTokenizer,
        )

        # ------------------------------------------------------
        # AMD ROCm workaround
        #
        # На AMD PyTorch использует интерфейс "cuda",
        # но внутри работает через HIP/ROCm.
        #
        # На Radeon 780M MIOpen может падать на LSTM:
        #
        # RuntimeError: miopenStatusUnknownError
        #
        # Поэтому для GLiNER отключаем оптимизированный
        # MIOpen/cuDNN RNN backend.
        #
        # Это НЕ переводит модель на CPU.
        # Вычисления остаются на GPU.
        # ------------------------------------------------------

        if (
            device == "cuda"
            and torch.version.hip is not None
        ):
            print(
                "AMD ROCm detected. "
                "Disabling MIOpen/cuDNN RNN backend "
                "for GLiNER."
            )

            torch.backends.cudnn.enabled = False

        model = GLiNER.from_pretrained(
            model_id
        ).to(device)

        if hasattr(model, "eval"):
            model.eval()

        tokenizer = (
            AutoTokenizer.from_pretrained(
                "microsoft/mdeberta-v3-base"
            )
        )

        def builder(n):
            ids = tokenizer(
                text,
                add_special_tokens=False,
                truncation=True,
                max_length=n,
            )["input_ids"]

            sample = tokenizer.decode(
                ids,
                skip_special_tokens=True,
            )

            def run():
                with torch.inference_mode():
                    model.predict_entities(
                        sample,
                        GLINER_LABELS,
                        threshold=0.5,
                    )

            return run, lambda: None

        return (
            model,
            tokenizer,
            builder,
        )

    # ==========================================================
    # SpanMarker
    # ==========================================================

    if kind == "spanmarker":
        from span_marker import (
            SpanMarkerModel,
        )

        from transformers import (
            AutoTokenizer,
        )

        model = (
            SpanMarkerModel.from_pretrained(
                model_id
            ).to(device)
        )

        tokenizer = (
            AutoTokenizer.from_pretrained(
                "bert-base-multilingual-cased"
            )
        )

        def builder(n):
            ids = tokenizer(
                text,
                add_special_tokens=False,
                truncation=True,
                max_length=max(
                    1,
                    n - 2,
                ),
            )["input_ids"]

            sample = tokenizer.decode(
                ids,
                skip_special_tokens=True,
            )

            def run():
                with torch.inference_mode():
                    model.predict(sample)

            return run, lambda: None

        return (
            model,
            tokenizer,
            builder,
        )

    # ==========================================================
    # Token Classification
    # ==========================================================

    if kind == "token_classification":
        from transformers import (
            AutoTokenizer,
            AutoModelForTokenClassification,
        )

        tokenizer = (
            AutoTokenizer.from_pretrained(
                model_id
            )
        )

        model = (
            AutoModelForTokenClassification
            .from_pretrained(model_id)
            .to(device)
            .eval()
        )

        def builder(n):
            batch = fixed_batch(
                tokenizer,
                text,
                n,
            )

            batch = {
                key: value.to(device)
                for key, value
                in batch.items()
            }

            def run():
                with torch.inference_mode():
                    model(**batch)

            return run, lambda: None

        return (
            model,
            tokenizer,
            builder,
        )

    # ==========================================================
    # Qwen
    # ==========================================================

    if kind in (
        "qwen",
        "qwen3",
    ):
        from transformers import (
            AutoTokenizer,
            AutoModelForCausalLM,
        )

        tokenizer = (
            AutoTokenizer.from_pretrained(
                model_id
            )
        )

        dtype = (
            torch.float16
            if device == "cuda"
            else torch.float32
        )

        model = (
            AutoModelForCausalLM
            .from_pretrained(
                model_id,
                torch_dtype=dtype,
            )
            .to(device)
            .eval()
        )

        instruction = (
            "Extract key words or short key phrases "
            "from the text. "
            "Preserve the source language and return "
            "only a JSON array. Text: "
        )

        def builder(n):
            batch = tokenizer(
                instruction + text,
                return_tensors="pt",
                truncation=True,
                max_length=n,
                padding="max_length",
            )

            batch = {
                key: value.to(device)
                for key, value
                in batch.items()
            }

            def run():
                with torch.inference_mode():
                    model.generate(
                        **batch,
                        max_new_tokens=(
                            GEN_MAX_NEW_TOKENS
                        ),
                        do_sample=False,
                        use_cache=True,
                        pad_token_id=(
                            tokenizer.eos_token_id
                        ),
                    )

            return run, lambda: None

        return (
            model,
            tokenizer,
            builder,
        )

    # ==========================================================
    # ruT5
    # ==========================================================

    if kind == "rut5":
        from transformers import (
            AutoTokenizer,
            AutoModelForSeq2SeqLM,
        )

        tokenizer = (
            AutoTokenizer.from_pretrained(
                model_id,
                use_fast=False,
            )
        )

        model = (
            AutoModelForSeq2SeqLM
            .from_pretrained(model_id)
            .to(device)
            .eval()
        )

        def builder(n):
            batch = fixed_batch(
                tokenizer,
                text,
                n,
                prefix=meta.get(
                    "prefix",
                    "keyphrase: ",
                ),
            )

            batch = {
                key: value.to(device)
                for key, value
                in batch.items()
            }

            def run():
                with torch.inference_mode():
                    model.generate(
                        **batch,
                        max_new_tokens=(
                            GEN_MAX_NEW_TOKENS
                        ),
                        num_beams=1,
                        do_sample=False,
                    )

            return run, lambda: None

        return (
            model,
            tokenizer,
            builder,
        )

    raise ValueError(
        f"Unsupported loader: {kind}"
    )


def main():
    args = args_parse()

    meta = REGISTRY[
        args.model
    ]

    # ==========================================================
    # GPU availability check
    # ==========================================================

    if (
        args.device == "cuda"
        and not torch.cuda.is_available()
    ):
        for requested in LENGTHS:
            row = base_row(
                args,
                meta,
                requested,
            )

            row.update(
                status="skipped",
                error=(
                    "CUDA/ROCm GPU unavailable "
                    "in current PyTorch environment"
                ),
            )

            append_row(
                args.output,
                row,
            )

        print(
            "GPU unavailable; "
            "rows marked as skipped."
        )

        return 0

    try:
        print(
            f"Loading "
            f"{meta['model_id']} "
            f"on {args.device}..."
        )

        (
            model,
            tokenizer,
            builder,
        ) = load_adapter(
            meta,
            args.device,
        )

        print("Loaded.")

        for requested in LENGTHS:
            effective = min(
                requested,
                meta["max_input_tokens"],
            )

            note = meta["notes"]

            if effective < requested:
                note += (
                    f" Requested {requested}, "
                    f"but official/configured "
                    f"limit is "
                    f"{meta['max_input_tokens']}; "
                    f"effective={effective}."
                )

            # Отмечаем workaround в результате
            if (
                args.model == "gliner"
                and args.device == "cuda"
                and torch.version.hip
                is not None
            ):
                note += (
                    " AMD ROCm: "
                    "MIOpen/cuDNN RNN backend "
                    "disabled for GLiNER "
                    "because of LSTM "
                    "compatibility issue."
                )

            print(
                f"{args.model} "
                f"{args.device}: "
                f"requested={requested}, "
                f"effective={effective}"
            )

            run, cleanup = builder(
                effective
            )

            try:
                (
                    avg,
                    minimum,
                    maximum,
                    peak,
                    delta,
                    metric,
                ) = timed(
                    run,
                    args.device,
                    args.warmup,
                    args.runs,
                )

            finally:
                cleanup()

            row = base_row(
                args,
                meta,
                requested,
            )

            row.update(
                effective_tokens=effective,
                status="ok",
                average_time_ms=round(
                    avg,
                    2,
                ),
                min_time_ms=round(
                    minimum,
                    2,
                ),
                max_time_ms=round(
                    maximum,
                    2,
                ),
                peak_memory_mb=round(
                    peak,
                    2,
                ),
                inference_memory_delta_mb=round(
                    delta,
                    2,
                ),
                memory_metric=metric,
                note=note,
                error="",
            )

            append_row(
                args.output,
                row,
            )

            print(
                f"avg="
                f"{row['average_time_ms']} ms "
                f"| peak="
                f"{row['peak_memory_mb']} MB"
            )

        del model

        gc.collect()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return 0

    except Exception as error:
        tb = traceback.format_exc()

        print(tb)

        for requested in LENGTHS:
            row = base_row(
                args,
                meta,
                requested,
            )

            row.update(
                status="error",
                error=(
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            )

            append_row(
                args.output,
                row,
            )

        error_log = (
            RESULTS_DIR
            / "benchmark_errors.log"
        )

        with error_log.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(
                f"\n===== "
                f"{args.model}/"
                f"{args.device} =====\n"
                f"{tb}\n"
            )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())