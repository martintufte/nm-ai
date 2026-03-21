"""Training pipeline for Norgesgruppen grocery product detection.

Two-stage approach:
1. Fine-tune YOLOv8 for detection (single-class) -- maximizes 70% detection mAP
2. Fine-tune YOLOv8 for detection+classification (multi-class) -- adds 30% classification mAP

Usage:
    # Step 1: Convert data to YOLO format
    python -m norgesgruppen.data.convert --single-class

    # Step 2: Train detection-only baseline
    python -m norgesgruppen.train --mode detect

    # Step 3: Convert data with all classes
    python -m norgesgruppen.data.convert

    # Step 4: Train multi-class model
    python -m norgesgruppen.train --mode classify

    # Step 5: Export best weights
    python -m norgesgruppen.train --mode export
"""

import argparse
import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import torch
from ultralytics import YOLO

LOGGER = logging.getLogger(__name__)


YOLO_DATA = Path(__file__).parent / "data" / "yolo" / "dataset.yaml"
RUNS_DIR = Path(__file__).parent / "runs"


@contextmanager
def working_directory(path: Path) -> Generator[None, Any]:
    """Temporarily switch cwd so Ultralytics side-effect downloads stay contained."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def resolve_training_device(device: str = "auto") -> str:
    """Resolve the training device and fail fast on broken CUDA setups."""
    normalized = device.strip().lower()
    if normalized != "auto":
        return device

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        LOGGER.info("Using CUDA device 0: %s", gpu_name)
        return "0"

    cuda_device_count = torch.cuda.device_count()
    if cuda_device_count > 0:
        cuda_version = torch.version.cuda or "unknown"
        msg = (
            "CUDA device detected, but PyTorch cannot initialize it. "
            f"torch.version.cuda={cuda_version}, cuda_device_count={cuda_device_count}. "
            "This usually means the NVIDIA driver is too old for the installed PyTorch CUDA build. "
            "Update the driver or install a compatible PyTorch build before training."
        )
        raise RuntimeError(msg)

    LOGGER.info("No CUDA device available, training on CPU")
    return "cpu"


def train_detection(
    model_size: str = "m",
    epochs: int = 50,
    imgsz: int = 1280,
    batch: int = 4,
    resume: bool = False,
    device: str = "auto",
) -> Path:
    """Train single-class detection model (maximizes detection mAP).

    Args:
        model_size: YOLOv8 model size: n/s/m/l/x
        epochs: Training epochs
        imgsz: Input image size (larger = better for small objects on shelves)
        batch: Batch size (adjust for GPU memory)
        resume: Resume from last checkpoint
        device: "cuda", "cpu" or "auto
    """
    model_name = f"yolov8{model_size}.pt"
    model = YOLO(model_name)
    train_device = resolve_training_device(device)

    with working_directory(RUNS_DIR):
        _results = model.train(
            data=str(YOLO_DATA),
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=train_device,
            project=str(RUNS_DIR),
            name="detect",
            exist_ok=True,
            resume=resume,
            # Augmentation for dense shelf images
            mosaic=0.5,
            mixup=0.1,
            copy_paste=0.1,
            # Optimizer
            optimizer="AdamW",
            lr0=0.001,
            lrf=0.01,
            warmup_epochs=3,
            # Saving
            save_period=10,
            plots=True,
        )

    best_path = RUNS_DIR / "detect" / "weights" / "best.pt"
    LOGGER.info("Best weights: %s", best_path)
    return best_path


def train_classification(
    model_size: str = "m",
    epochs: int = 80,
    imgsz: int = 1280,
    batch: int = 4,
    pretrained_detect: Path | None = None,
    resume: bool = False,
    device: str = "auto",
) -> Path:
    """Train multi-class model (detection + classification).

    Can optionally start from a pretrained detection model.
    """
    if pretrained_detect and pretrained_detect.exists():
        LOGGER.info("Starting from pretrained: %s", pretrained_detect)
        model = YOLO(str(pretrained_detect))
    else:
        model_name = f"yolov8{model_size}.pt"
        model = YOLO(model_name)
    train_device = resolve_training_device(device)

    with working_directory(RUNS_DIR):
        _results = model.train(
            data=str(YOLO_DATA),
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=train_device,
            project=str(RUNS_DIR),
            name="classify",
            exist_ok=True,
            resume=resume,
            # Augmentation
            mosaic=0.5,
            mixup=0.1,
            copy_paste=0.1,
            # Optimizer
            optimizer="AdamW",
            lr0=0.0005,
            lrf=0.01,
            warmup_epochs=5,
            # More epochs for 356 classes
            patience=20,
            save_period=10,
            plots=True,
        )

    best_path = RUNS_DIR / "classify" / "weights" / "best.pt"
    LOGGER.info("Best weights: %s", best_path)
    return best_path


def export_model(weights_path: Path, format: str = "torchscript") -> Path:
    """Export model for submission.

    Supported formats: torchscript, onnx, engine (TensorRT)
    """
    model = YOLO(str(weights_path))
    export_path = model.export(format=format, half=True, imgsz=1280)
    LOGGER.info("Exported: %s", export_path)
    return Path(export_path)


def evaluate(weights_path: Path) -> None:
    """Run validation on the val split."""
    model = YOLO(str(weights_path))
    metrics = model.val(data=str(YOLO_DATA), imgsz=1280, plots=True)
    LOGGER.info("mAP50:    %.4f", metrics.box.map50)
    LOGGER.info("mAP50-95: %.4f", metrics.box.map)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train Norgesgruppen detection model")
    parser.add_argument(
        "--mode",
        choices=["detect", "classify", "export", "eval"],
        required=True,
    )
    parser.add_argument("--model-size", default="m", choices=["n", "s", "m", "l", "x"])
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--device",
        default="auto",
        help="Training device for Ultralytics (default: auto, prefers CUDA and fails on broken CUDA)",
    )
    parser.add_argument("--weights", type=Path, help="Weights path for export/eval")
    args = parser.parse_args()

    if args.mode == "detect":
        train_detection(
            model_size=args.model_size,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            resume=args.resume,
            device=args.device,
        )
    elif args.mode == "classify":
        detect_weights = RUNS_DIR / "detect" / "weights" / "best.pt"
        train_classification(
            model_size=args.model_size,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            pretrained_detect=detect_weights,
            resume=args.resume,
            device=args.device,
        )
    elif args.mode == "export":
        weights = args.weights or RUNS_DIR / "classify" / "weights" / "best.pt"
        export_model(weights)
    elif args.mode == "eval":
        weights = args.weights or RUNS_DIR / "classify" / "weights" / "best.pt"
        evaluate(weights)


if __name__ == "__main__":
    main()
