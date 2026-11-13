import platform
import sys
from importlib.metadata import (
    PackageNotFoundError,
    version,
)


PACKAGES = [
    "torch",
    "transformers",
    "sentence-transformers",
    "huggingface-hub",
    "datasets",
    "gliner",
    "span-marker",
    "FlagEmbedding",
    "accelerate",
    "peft",
    "sentencepiece",
    "protobuf",
    "tiktoken",
    "safetensors",
    "httpx",
    "psutil",
]


def package_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return "NOT INSTALLED"


def main():
    print("=" * 70)
    print("BENCHMARK ENVIRONMENT")
    print("=" * 70)

    print()
    print("System")
    print("-" * 70)

    print(
        f"Python: "
        f"{sys.version.split()[0]}"
    )

    print(
        f"Executable: "
        f"{sys.executable}"
    )

    print(
        f"OS: "
        f"{platform.system()} "
        f"{platform.release()}"
    )

    print(
        f"Architecture: "
        f"{platform.machine()}"
    )

    print()
    print("Packages")
    print("-" * 70)

    for package in PACKAGES:
        print(
            f"{package}: "
            f"{package_version(package)}"
        )

    print()
    print("PyTorch / GPU")
    print("-" * 70)

    try:
        import torch

    except Exception as error:
        print(
            "PyTorch import failed:"
        )

        print(error)

        return 1

    print(
        f"PyTorch: "
        f"{torch.__version__}"
    )

    print(
        f"CUDA build: "
        f"{torch.version.cuda}"
    )

    print(
        f"HIP/ROCm build: "
        f"{torch.version.hip}"
    )

    gpu_available = (
        torch.cuda.is_available()
    )

    print(
        f"GPU available: "
        f"{gpu_available}"
    )

    if gpu_available:
        try:
            device_count = (
                torch.cuda.device_count()
            )

            print(
                f"GPU count: "
                f"{device_count}"
            )

            for index in range(
                device_count
            ):
                name = (
                    torch.cuda
                    .get_device_name(index)
                )

                properties = (
                    torch.cuda
                    .get_device_properties(
                        index
                    )
                )

                memory_gb = (
                    properties.total_memory
                    / (1024 ** 3)
                )

                print(
                    f"GPU {index}: "
                    f"{name}"
                )

                print(
                    f"GPU {index} memory: "
                    f"{memory_gb:.2f} GB"
                )

        except Exception as error:
            print(
                "Could not read GPU details:"
            )

            print(error)

    print()
    print("Backend")
    print("-" * 70)

    if torch.version.hip:
        print(
            "Detected AMD ROCm/HIP backend."
        )

        print(
            "Note: PyTorch still uses "
            "'cuda' as the device name "
            "for ROCm."
        )

    elif torch.version.cuda:
        print(
            "Detected NVIDIA CUDA backend."
        )

    else:
        print(
            "No CUDA/ROCm backend detected. "
            "CPU benchmarking is available."
        )

    print()
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())