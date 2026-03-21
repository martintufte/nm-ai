"""Utilities for tracking runs and saving artifacts."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from pathlib import Path

EXPERIMENTS_DIRNAME = "experiments"
LEGACY_OUTPUT_DIRNAME = "output"


def get_package_root() -> Path:
    return Path(__file__).resolve().parent


def get_run_root() -> Path:
    return get_package_root() / EXPERIMENTS_DIRNAME


def get_legacy_run_root() -> Path:
    return get_package_root() / LEGACY_OUTPUT_DIRNAME


def create_run_dir(method: str) -> Path:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    safe_method = method.replace(" ", "_")
    run_dir = get_run_root() / f"{timestamp}_{safe_method}"
    (run_dir / "model_weights").mkdir(parents=True, exist_ok=True)
    return run_dir


def copy_weights(weights_dir: Path, dest_dir: Path) -> list[Path]:
    copied: list[Path] = []
    for name in ["best.pt", "model.pt", "best.onnx", "model.onnx"]:
        src = weights_dir / name
        if src.exists():
            data = src.read_bytes()
            dst = dest_dir / name
            dst.write_bytes(data)
            copied.append(dst)
    return copied


def copy_predictions(predictions_path: Path, dest_dir: Path) -> Path:
    dest = dest_dir / "predictions.json"
    dest.write_text(predictions_path.read_text())
    return dest


def resolve_run_dir_from_predictions(predictions_path: Path) -> Path | None:
    for run_root in (get_run_root(), get_legacy_run_root()):
        try:
            rel = predictions_path.resolve().relative_to(run_root)
        except ValueError:
            continue
        if not rel.parts:
            continue
        return run_root / rel.parts[0]
    return None
