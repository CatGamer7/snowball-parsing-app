"""Собирает минимальный автономный HF-кэш двух моделей, без токенов и symlink."""
import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
import shutil

REPOSITORIES = {
    "urchade/gliner_multi-v2.1": ["*.json", "*.txt", "*.model", "pytorch_model.bin", "README*", "LICENSE*"],
    "microsoft/mdeberta-v3-base": ["*.json", "*.txt", "*.model", "README*", "LICENSE*"],
}


def selected(relative: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns)


def copy_snapshot(source: Path, destination: Path, patterns: list[str]):
    files = []
    destination.mkdir(parents=True, exist_ok=True)
    for file in sorted(source.rglob("*")):
        relative = file.relative_to(source).as_posix()
        if not file.is_file() or not selected(relative, patterns):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)  # Разыменовываем HF symlink, не копируем весь blobs-кэш.
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            while block := stream.read(4 * 1024 * 1024):
                digest.update(block)
        files.append({"path": relative, "bytes": target.stat().st_size, "sha256": digest.hexdigest()})
    return files


def prepare(destination: Path, *, local_only: bool = False):
    from huggingface_hub import hf_hub_download, snapshot_download
    staging = destination.with_name(destination.name + "-staging")
    if staging.exists():
        shutil.rmtree(staging)
    manifest = {}
    for repo, patterns in REPOSITORIES.items():
        config = "gliner_config.json" if repo.startswith("urchade/") else "config.json"
        revision = "main"
        # Сначала выбираем уже проверенную пользователем ревизию из кэша.
        try:
            cached = Path(hf_hub_download(repo, config, local_files_only=True))
            revision = cached.parent.name
        except Exception:
            if local_only:
                raise
        print(f"Preparing {repo} @ {revision}", flush=True)
        snapshot = Path(snapshot_download(repo, revision=revision, allow_patterns=patterns,
                                          local_files_only=local_only))
        revision = snapshot.name
        repo_dir = staging / "hub" / ("models--" + repo.replace("/", "--"))
        files = copy_snapshot(snapshot, repo_dir / "snapshots" / revision, patterns)
        (repo_dir / "refs").mkdir(parents=True)
        (repo_dir / "refs/main").write_text(revision, encoding="utf-8")
        required = [config, "pytorch_model.bin"] if repo.startswith("urchade/") else [config, "spm.model"]
        for name in required:
            if not (repo_dir / "snapshots" / revision / name).is_file():
                raise RuntimeError(f"Missing model file: {repo}/{name}")
        manifest[repo] = {"revision": revision, "files": files}
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    if destination.exists():
        shutil.rmtree(destination)
    staging.rename(destination)
    print("Model cache ready:", destination, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--local-only", action="store_true")
    arguments = parser.parse_args()
    prepare(arguments.destination.resolve(), local_only=arguments.local_only)
