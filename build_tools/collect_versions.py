"""Фиксирует версии реально работающих runtime-зависимостей, без pytest и CUDA."""
import importlib.metadata as metadata
import json
from pathlib import Path
import sys
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOTS = ["fastapi", "uvicorn", "pydantic", "httpx", "python-dotenv", "gliner",
         "transformers", "huggingface-hub", "torch", "sentencepiece", "protobuf",
         "tiktoken", "safetensors", "numpy"]


def collect():
    pending = list(ROOTS)
    found = {}
    while pending:
        name = canonicalize_name(pending.pop())
        if name in found or name.startswith(("nvidia-", "cuda-")) or name in {"triton", "torchvision", "torchaudio"}:
            continue
        distribution = metadata.distribution(name)
        found[name] = distribution.version
        for dependency in distribution.requires or []:
            requirement = Requirement(dependency)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return found


if __name__ == "__main__":
    destination = Path(sys.argv[1])
    destination.mkdir(parents=True, exist_ok=True)
    versions = collect()
    (destination / "runtime-versions.json").write_text(
        json.dumps(versions, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    (destination / "runtime-requirements.txt").write_text(
        "\n".join(f"{name}=={version}" for name, version in sorted(versions.items()) if name != "torch") + "\n",
        encoding="utf-8",
    )
    print("Runtime versions captured:", len(versions), "packages")
