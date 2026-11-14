from pathlib import Path
from importlib.metadata import distributions
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).parent
metadata = []
for distribution in distributions():
    name = distribution.metadata.get("Name")
    if name:
        metadata += copy_metadata(name)

hidden = [
    "gliner", "gliner.model", "torch", "transformers", "sentencepiece", "safetensors.torch",
    "transformers.models.auto.configuration_auto", "transformers.models.auto.modeling_auto",
    "transformers.models.auto.tokenization_auto",
    "transformers.models.deberta_v2.configuration_deberta_v2",
    "transformers.models.deberta_v2.modeling_deberta_v2",
    "transformers.models.deberta_v2.tokenization_deberta_v2",
    "transformers.models.deberta_v2.tokenization_deberta_v2_fast",
    "uvicorn.logging", "uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl",
    "uvicorn.lifespan.on", "tiktoken_ext.openai_public",
]
a = Analysis(
    [str(root / "backend/entrypoint.py")],
    pathex=[str(root / "backend")],
    binaries=[],
    datas=[(str(root / "ml/gliner/gliner_inference.py"), "ml/gliner")] + metadata,
    hiddenimports=hidden,
    hookspath=[str(root / "build_tools/hooks")],
    excludes=["tkinter", "PyQt5", "PyQt6", "PySide6", "IPython", "jupyter", "pytest",
              "tensorflow", "jax", "flax", "torchvision", "torchaudio", "bitsandbytes",
              "deepspeed", "onnxruntime", "onnx"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="snowball-backend",
          debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="snowball-backend")
