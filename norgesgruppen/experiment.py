"""Experiment runner for Norgesgruppen grocery detection.

Runs training + evaluation in one go, saves configs and results for reproducibility.
After training, sweeps conf/iou thresholds to find optimal inference settings.

Usage:
    # Quick test (2 epochs, nano model)
    python -m norgesgruppen.experiment --name test --model-size n --epochs 2 --imgsz 640

    # Detection sweep
    python -m norgesgruppen.experiment --name detect_yolov8s --model-size s --epochs 50
    python -m norgesgruppen.experiment --name detect_yolov8m --model-size m --epochs 50

    # Multi-class
    python -m norgesgruppen.experiment --name classify_m --model-size m --epochs 80 --multi-class
"""

import argparse
import json
import logging
import os
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC
from datetime import datetime
from pathlib import Path

import torch
from ultralytics import YOLO

from norgesgruppen.data.convert import convert_coco_to_yolo
from norgesgruppen.evaluate import evaluate_map

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)

EXPERIMENTS_DIR = Path(__file__).parent / "experiments"
WEIGHTS_DIR = Path(__file__).parent / "weights"
DATA_DIR = Path(__file__).parent / "data"
ANNOTATIONS_PATH = DATA_DIR / "NM_NGD_coco_dataset" / "train" / "annotations.json"

# Threshold grids for post-training sweep
CONF_THRESHOLDS = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5]
IOU_THRESHOLDS = [0.3, 0.4, 0.45, 0.5, 0.6, 0.7]


@contextmanager
def working_directory(path: Path):
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


def run_experiment(
    name: str,
    model_size: str = "m",
    epochs: int = 50,
    imgsz: int = 1280,
    batch: int = -1,
    multi_class: bool = False,
    pretrained_weights: str | None = None,
    max_detections: int = 300,
    mosaic: float = 0.5,
    mixup: float = 0.1,
    copy_paste: float = 0.1,
    optimizer: str = "AdamW",
    lr0: float = 0.001,
    lrf: float = 0.01,
    warmup_epochs: int = 3,
    patience: int = 20,
    val_fraction: float = 0.15,
    seed: int = 42,
    model_variant: str = "yolov8",
    device: str = "auto",
) -> Path:
    """Run a complete experiment: convert data -> train -> sweep thresholds -> evaluate."""
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    exp_dir = EXPERIMENTS_DIR / f"{timestamp}_{name}"
    exp_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "name": name,
        "timestamp": timestamp,
        "model_variant": model_variant,
        "model_size": model_size,
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
        "multi_class": multi_class,
        "pretrained_weights": pretrained_weights,
        "max_detections": max_detections,
        "mosaic": mosaic,
        "mixup": mixup,
        "copy_paste": copy_paste,
        "optimizer": optimizer,
        "lr0": lr0,
        "lrf": lrf,
        "warmup_epochs": warmup_epochs,
        "patience": patience,
        "val_fraction": val_fraction,
        "seed": seed,
        "device": device,
    }
    (exp_dir / "config.json").write_text(json.dumps(config, indent=2))
    LOGGER.info("Experiment: %s", exp_dir.name)

    # Step 1: Convert data
    single_class = not multi_class
    LOGGER.info("Converting data (single_class=%s)...", single_class)
    dataset_yaml = convert_coco_to_yolo(
        val_fraction=val_fraction,
        single_class=single_class,
        seed=seed,
    )

    # Step 2: Train
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    if pretrained_weights:
        LOGGER.info("Loading pretrained: %s", pretrained_weights)
        model = YOLO(pretrained_weights)
    else:
        model_name = f"{model_variant}{model_size}.pt"
        # Download pretrained weights to weights/ dir, not cwd
        local_weights = WEIGHTS_DIR / model_name
        if not local_weights.exists():
            LOGGER.info("Downloading %s to %s...", model_name, WEIGHTS_DIR)
            tmp_model = YOLO(model_name)
            # ultralytics downloads to cwd; move it
            cwd_weights = Path(model_name)
            if cwd_weights.exists():
                cwd_weights.rename(local_weights)
            del tmp_model
        LOGGER.info("Starting from: %s", local_weights)
        model = YOLO(str(local_weights))

    train_device = resolve_training_device(device)
    LOGGER.info(
        "Starting training (%d epochs, imgsz=%d, device=%s)...",
        epochs,
        imgsz,
        train_device,
    )
    with working_directory(WEIGHTS_DIR):
        _results = model.train(
            data=str(dataset_yaml),
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=train_device,
            project=str(exp_dir),
            name="train",
            exist_ok=True,
            mosaic=mosaic,
            mixup=mixup,
            copy_paste=copy_paste,
            optimizer=optimizer,
            lr0=lr0,
            lrf=lrf,
            warmup_epochs=warmup_epochs,
            patience=patience,
            save_period=max(10, epochs // 5),
            plots=True,
            verbose=True,
        )

    # Step 3: Copy best weights to central weights/ dir
    best_weights = exp_dir / "train" / "weights" / "best.pt"
    if not best_weights.exists():
        best_weights = exp_dir / "train" / "weights" / "last.pt"
    saved_weights = WEIGHTS_DIR / f"{name}.pt"
    saved_weights.write_bytes(best_weights.read_bytes())
    LOGGER.info("Saved trained weights: %s", saved_weights)

    LOGGER.info("Running inference + threshold sweep with: %s", best_weights)
    sweep_results = run_inference_and_sweep(
        weights_path=best_weights,
        annotations_path=ANNOTATIONS_PATH,
        dataset_yaml=dataset_yaml,
        max_detections=max_detections,
        imgsz=imgsz,
        exp_dir=exp_dir,
    )

    # Save full results
    results = {
        **config,
        "best_settings": sweep_results["best"],
        "sweep": sweep_results["sweep"],
    }
    (exp_dir / "results.json").write_text(json.dumps(results, indent=2))

    # Append best result to leaderboard
    best = sweep_results["best"]
    leaderboard_path = EXPERIMENTS_DIR / "leaderboard.txt"
    with leaderboard_path.open("a") as f:
        f.write(
            f"{best['final_score']:.6f}\t"
            f"det={best['detection_map']:.4f}\t"
            f"cls={best['classification_map']:.4f}\t"
            f"conf={best['conf']}\t"
            f"iou={best['iou']}\t"
            f"{exp_dir.name}\n",
        )

    LOGGER.info("=" * 60)
    LOGGER.info("RESULTS: %s", exp_dir.name)
    LOGGER.info("  Best conf=%.2f  iou=%.2f", best["conf"], best["iou"])
    LOGGER.info("  Detection mAP@0.5:      %.4f (70%%)", best["detection_map"])
    LOGGER.info("  Classification mAP@0.5: %.4f (30%%)", best["classification_map"])
    LOGGER.info("  Final score:            %.4f", best["final_score"])
    LOGGER.info("  Predictions: %s", exp_dir / "predictions.json")
    LOGGER.info("  Weights:     %s", best_weights)
    LOGGER.info("=" * 60)

    return exp_dir


def run_inference_and_sweep(
    weights_path: Path,
    annotations_path: Path,
    dataset_yaml: Path,
    max_detections: int = 300,
    imgsz: int = 1280,
    exp_dir: Path | None = None,
) -> dict:
    """Run inference once at low conf, then sweep thresholds to find best settings.

    Returns dict with 'best' (best settings+scores) and 'sweep' (all combos).
    """
    model = YOLO(str(weights_path))

    # Get val images
    yolo_dir = dataset_yaml.parent
    val_images_dir = yolo_dir / "val" / "images"
    image_paths = sorted(val_images_dir.glob("*.jpg")) + sorted(val_images_dir.glob("*.jpeg"))
    LOGGER.info(
        "Running inference on %d val images (low conf=0.01 to collect all detections)...",
        len(image_paths),
    )

    # Load ground truth
    with annotations_path.open() as f:
        ground_truth = json.load(f)

    categories = ground_truth.get("categories", [])
    yolo_idx_to_cat_id = {idx: cat["id"] for idx, cat in enumerate(categories)}

    # Run inference once with very low conf to get all candidate detections
    raw_predictions = []
    with torch.no_grad():
        for img_path in image_paths:
            results = model.predict(
                source=str(img_path.resolve()),
                conf=0.01,
                iou=0.7,  # permissive NMS — we filter later
                imgsz=imgsz,
                max_det=max_detections,
                verbose=False,
            )

            image_id = img_path.stem
            for result in results:
                boxes = result.boxes
                if boxes is None or len(boxes) == 0:
                    continue
                for i in range(len(boxes)):
                    x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
                    yolo_cls = int(boxes.cls[i].cpu().item())
                    cat_id = yolo_idx_to_cat_id.get(yolo_cls, 0)

                    raw_predictions.append(
                        {
                            "image_id": image_id,
                            "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                            "category_id": cat_id,
                            "score": float(boxes.conf[i].cpu().item()),
                        },
                    )

    LOGGER.info("Collected %d raw detections, sweeping thresholds...", len(raw_predictions))

    # Filter ground truth to val images only
    val_image_stems = {p.stem for p in image_paths}
    val_gt_images = [
        img for img in ground_truth["images"] if Path(img["file_name"]).stem in val_image_stems
    ]
    val_image_ids = {img["id"] for img in val_gt_images}
    val_gt_annotations = [
        ann for ann in ground_truth["annotations"] if ann["image_id"] in val_image_ids
    ]
    val_ground_truth = {
        "images": val_gt_images,
        "annotations": val_gt_annotations,
        "categories": categories,
    }

    # Sweep conf/iou thresholds
    sweep = []
    best = {"final_score": -1.0}

    for conf in CONF_THRESHOLDS:
        # Filter by confidence
        filtered = [p for p in raw_predictions if p["score"] >= conf]

        for iou in IOU_THRESHOLDS:
            # Apply NMS per image (approximate: skip boxes with high overlap and lower score)
            nms_filtered = apply_nms(filtered, iou)

            det_map = evaluate_map(nms_filtered, val_ground_truth, ignore_class=True)
            cls_map = evaluate_map(nms_filtered, val_ground_truth, ignore_class=False)
            score = 0.7 * det_map + 0.3 * cls_map

            entry = {
                "conf": conf,
                "iou": iou,
                "detection_map": det_map,
                "classification_map": cls_map,
                "final_score": score,
                "num_predictions": len(nms_filtered),
            }
            sweep.append(entry)

            if score > best["final_score"]:
                best = entry
                best_predictions = nms_filtered

            LOGGER.info(
                "  conf=%.2f iou=%.2f → det=%.4f cls=%.4f score=%.4f (%d preds)",
                conf,
                iou,
                det_map,
                cls_map,
                score,
                len(nms_filtered),
            )

    # Save best predictions
    if exp_dir and best["final_score"] >= 0:
        (exp_dir / "predictions.json").write_text(json.dumps(best_predictions, indent=2))
        (exp_dir / "best_settings.json").write_text(json.dumps(best, indent=2))

    return {"best": best, "sweep": sweep}


def apply_nms(predictions: list[dict], iou_threshold: float) -> list[dict]:
    """Simple per-image NMS on pre-filtered predictions."""
    by_image: dict[str, list[dict]] = defaultdict(list)
    for p in predictions:
        by_image[p["image_id"]].append(p)

    result = []
    for preds in by_image.values():
        preds_sorted = sorted(preds, key=lambda x: x["score"], reverse=True)
        keep = []
        for pred in preds_sorted:
            suppressed = False
            for kept in keep:
                if _iou(pred["bbox"], kept["bbox"]) > iou_threshold:
                    suppressed = True
                    break
            if not suppressed:
                keep.append(pred)
        result.extend(keep)
    return result


def _iou(box1: list[float], box2: list[float]) -> float:
    """IoU between two [x, y, w, h] boxes."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2
    xi1 = max(x1, x2)
    yi1 = max(y1, y2)
    xi2 = min(x1 + w1, x2 + w2)
    yi2 = min(y1 + h1, y2 + h2)
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    union = w1 * h1 + w2 * h2 - inter
    return inter / union if union > 0 else 0.0


def run_eval_only(
    weights: str,
    name: str | None = None,
    imgsz: int = 1280,
    max_detections: int = 300,
    multi_class: bool = False,
    val_fraction: float = 0.15,
    seed: int = 42,
) -> Path:
    """Run inference + threshold sweep on an existing weights file (no training)."""
    weights_path = Path(weights)
    if not weights_path.exists():
        # Check weights/ dir
        weights_path = WEIGHTS_DIR / weights
    if not weights_path.exists():
        msg = f"Weights not found: {weights}"
        raise FileNotFoundError(msg)

    if name is None:
        name = f"eval_{weights_path.stem}"

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
    exp_dir = EXPERIMENTS_DIR / f"{timestamp}_{name}"
    exp_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "name": name,
        "timestamp": timestamp,
        "weights": str(weights_path),
        "imgsz": imgsz,
        "max_detections": max_detections,
        "multi_class": multi_class,
        "mode": "eval_only",
    }
    (exp_dir / "config.json").write_text(json.dumps(config, indent=2))
    LOGGER.info("Eval-only: %s", exp_dir.name)
    LOGGER.info("Weights:   %s", weights_path)

    single_class = not multi_class
    dataset_yaml = convert_coco_to_yolo(
        val_fraction=val_fraction,
        single_class=single_class,
        seed=seed,
    )

    sweep_results = run_inference_and_sweep(
        weights_path=weights_path,
        annotations_path=ANNOTATIONS_PATH,
        dataset_yaml=dataset_yaml,
        max_detections=max_detections,
        imgsz=imgsz,
        exp_dir=exp_dir,
    )

    results = {**config, "best_settings": sweep_results["best"], "sweep": sweep_results["sweep"]}
    (exp_dir / "results.json").write_text(json.dumps(results, indent=2))

    best = sweep_results["best"]
    leaderboard_path = EXPERIMENTS_DIR / "leaderboard.txt"
    with leaderboard_path.open("a") as f:
        f.write(
            f"{best['final_score']:.6f}\t"
            f"det={best['detection_map']:.4f}\t"
            f"cls={best['classification_map']:.4f}\t"
            f"conf={best['conf']}\t"
            f"iou={best['iou']}\t"
            f"{exp_dir.name}\n",
        )

    LOGGER.info("=" * 60)
    LOGGER.info("RESULTS: %s", exp_dir.name)
    LOGGER.info("  Best conf=%.2f  iou=%.2f", best["conf"], best["iou"])
    LOGGER.info("  Detection mAP@0.5:      %.4f (70%%)", best["detection_map"])
    LOGGER.info("  Classification mAP@0.5: %.4f (30%%)", best["classification_map"])
    LOGGER.info("  Final score:            %.4f", best["final_score"])
    LOGGER.info("=" * 60)

    return exp_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run detection experiment")
    sub = parser.add_subparsers(dest="command")

    # --- train (default when no subcommand) ---
    train_p = sub.add_parser("train", help="Train + evaluate")
    train_p.add_argument("--name", required=True, help="Experiment name")
    train_p.add_argument("--model-size", default="m", choices=["n", "s", "m", "l", "x"])
    train_p.add_argument(
        "--model-variant",
        default="yolov8",
        help="Model variant (yolov8, yolo11, etc.)",
    )
    train_p.add_argument("--epochs", type=int, default=50)
    train_p.add_argument("--imgsz", type=int, default=1280)
    train_p.add_argument("--batch", type=int, default=-1, help="Batch size (-1 for auto)")
    train_p.add_argument("--multi-class", action="store_true", help="Train with all 356 classes")
    train_p.add_argument("--pretrained-weights", type=str, help="Path to pretrained weights")
    train_p.add_argument("--lr0", type=float, default=0.001)
    train_p.add_argument("--mosaic", type=float, default=0.5)
    train_p.add_argument("--mixup", type=float, default=0.1)
    train_p.add_argument("--optimizer", default="AdamW")
    train_p.add_argument("--patience", type=int, default=20)
    train_p.add_argument("--val-fraction", type=float, default=0.15)
    train_p.add_argument("--seed", type=int, default=42)
    train_p.add_argument(
        "--device",
        default="auto",
        help="Training device for Ultralytics (default: auto, prefers CUDA and fails on broken CUDA)",
    )

    # --- eval (inference only) ---
    eval_p = sub.add_parser("eval", help="Run inference + threshold sweep on existing weights")
    eval_p.add_argument(
        "--weights", required=True, help="Path to .pt weights (or name in weights/)"
    )
    eval_p.add_argument("--name", help="Experiment name (default: eval_<weights_stem>)")
    eval_p.add_argument("--imgsz", type=int, default=1280)
    eval_p.add_argument("--multi-class", action="store_true")
    eval_p.add_argument("--val-fraction", type=float, default=0.15)
    eval_p.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    if args.command == "eval":
        run_eval_only(
            weights=args.weights,
            name=args.name,
            imgsz=args.imgsz,
            multi_class=args.multi_class,
            val_fraction=args.val_fraction,
            seed=args.seed,
        )
    else:
        # Default to train (also handles explicit "train" subcommand)
        if not hasattr(args, "name") or args.name is None:
            parser.error("train requires --name")
        run_experiment(
            name=args.name,
            model_size=args.model_size,
            model_variant=args.model_variant,
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            multi_class=args.multi_class,
            pretrained_weights=args.pretrained_weights,
            lr0=args.lr0,
            mosaic=args.mosaic,
            mixup=args.mixup,
            optimizer=args.optimizer,
            patience=args.patience,
            val_fraction=args.val_fraction,
            seed=args.seed,
            device=args.device,
        )


if __name__ == "__main__":
    main()
