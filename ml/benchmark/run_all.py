import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MODELS_FILE = ROOT / "models.json"
BENCHMARK_SCRIPT = ROOT / "benchmark_one.py"

RESULTS_DIR = ROOT / "results"
DEFAULT_RESULTS_FILE = RESULTS_DIR / "benchmark_results.csv"
ERROR_LOG = RESULTS_DIR / "benchmark_errors.log"


def load_models():
    if not MODELS_FILE.exists():
        raise FileNotFoundError(
            f"models.json not found: {MODELS_FILE}"
        )

    with MODELS_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def parse_args(model_names):
    parser = argparse.ArgumentParser(
        description=(
            "Run model benchmarks on CPU/GPU. "
            "Existing results are preserved by default."
        )
    )

    parser.add_argument(
        "--models",
        nargs="+",
        choices=model_names,
        help=(
            "Models to benchmark. "
            "If omitted, all models from models.json are used."
        ),
    )

    parser.add_argument(
        "--devices",
        nargs="+",
        choices=["cpu", "cuda"],
        default=["cpu", "cuda"],
        help="Devices to benchmark. Default: cpu cuda",
    )

    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help="Number of warmup runs. Default: 3",
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="Number of measured runs. Default: 10",
    )

    parser.add_argument(
        "--output",
        default=str(DEFAULT_RESULTS_FILE),
        help="Path to benchmark_results.csv",
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Delete old benchmark results and error log "
            "before starting."
        ),
    )

    parser.add_argument(
        "--append",
        action="store_true",
        help=(
            "Deprecated compatibility flag. "
            "Results are appended by default."
        ),
    )

    return parser.parse_args()


def reset_results(output_file):
    output_file = Path(output_file)

    files_to_remove = [
        output_file,
        ERROR_LOG,
    ]

    for path in files_to_remove:
        if path.exists():
            path.unlink()
            print(f"Removed old file: {path}")


def main():
    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    models = load_models()

    args = parse_args(
        list(models.keys())
    )

    selected_models = (
        args.models
        if args.models
        else list(models.keys())
    )

    if args.reset:
        reset_results(args.output)

    total = (
        len(selected_models)
        * len(args.devices)
    )

    current = 0
    failures = []

    print()
    print("=" * 70)
    print("MODEL BENCHMARK")
    print("=" * 70)

    print(
        f"Models: {', '.join(selected_models)}"
    )

    print(
        f"Devices: {', '.join(args.devices)}"
    )

    print(
        f"Warmup: {args.warmup}"
    )

    print(
        f"Measured runs: {args.runs}"
    )

    print(
        f"Results: {args.output}"
    )

    print()

    for model in selected_models:
        for device in args.devices:
            current += 1

            print()
            print("=" * 70)
            print(
                f"[{current}/{total}] "
                f"{model} / {device}"
            )
            print("=" * 70)

            command = [
                sys.executable,
                str(BENCHMARK_SCRIPT),
                "--model",
                model,
                "--device",
                device,
                "--warmup",
                str(args.warmup),
                "--runs",
                str(args.runs),
                "--output",
                str(args.output),
            ]

            result = subprocess.run(
                command,
                cwd=ROOT,
            )

            if result.returncode != 0:
                failures.append(
                    (model, device)
                )

                print()
                print(
                    "Model failed; "
                    "suite continues. "
                    "See results/benchmark_errors.log"
                )

    print()
    print("=" * 70)
    print("DONE")
    print("=" * 70)

    print(
        f"Results: "
        f"{Path(args.output).resolve()}"
    )

    print(
        f"Errors: "
        f"{ERROR_LOG.resolve()}"
    )

    if failures:
        print()
        print("Failed runs:")

        for model, device in failures:
            print(
                f"  - {model} / {device}"
            )

    else:
        print()
        print(
            "All requested benchmarks "
            "completed successfully."
        )


if __name__ == "__main__":
    main()