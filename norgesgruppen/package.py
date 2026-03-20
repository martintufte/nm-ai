"""Package an inference-only Norgesgruppen submission."""

import argparse
import json
import logging
import shutil
import zipfile
from datetime import UTC
from datetime import datetime
from pathlib import Path

LOGGER = logging.getLogger(__name__)

TASK_DIR = Path(__file__).parent
RUNS_DIR = TASK_DIR / "runs"
EXPERIMENTS_DIR = TASK_DIR / "experiments"
SUBMISSIONS_DIR = TASK_DIR / "submissions"
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
PACKAGED_RUN_PY_TEMPLATE = '''"""Norgesgruppen grocery product detection submission entry point."""

import argparse
import inspect
import json
import logging
from collections import OrderedDict
from pathlib import Path

import torch
from ultralytics import YOLO
from ultralytics.nn import modules as ultralytics_modules
from ultralytics.nn import tasks as ultralytics_tasks

LOGGER = logging.getLogger(__name__)

CONF_THRESHOLD = __CONF_THRESHOLD__
IOU_THRESHOLD = __IOU_THRESHOLD__
IMG_SIZE = __IMG_SIZE__
MAX_DETECTIONS = __MAX_DETECTIONS__


def allowlist_ultralytics_checkpoint_classes() -> None:
    """Allow trusted Ultralytics checkpoint classes for PyTorch 2.6+ loading."""
    add_safe_globals = getattr(torch.serialization, "add_safe_globals", None)
    if add_safe_globals is None:
        return

    safe_classes = []
    for module in (ultralytics_tasks, ultralytics_modules):
        for value in vars(module).values():
            if inspect.isclass(value):
                safe_classes.append(value)

    for value in vars(torch.nn).values():
        if inspect.isclass(value):
            safe_classes.append(value)

    safe_classes.append(OrderedDict)
    add_safe_globals(safe_classes)


def load_model(weights_dir: Path) -> YOLO:
    """Load YOLO model from packaged weights."""
    allowlist_ultralytics_checkpoint_classes()
    for name in ["best.pt", "model.pt"]:
        weights_path = weights_dir / name
        if weights_path.exists():
            model = YOLO(str(weights_path))
            model.fuse()
            return model
    raise FileNotFoundError(f"No model weights found in {weights_dir}")


def list_image_paths(images_dir: Path) -> list[Path]:
    """Enumerate task images in a stable order."""
    image_paths = []
    for pattern in ("img_*.jpg", "img_*.jpeg", "img_*.png"):
        image_paths.extend(images_dir.glob(pattern))
    return sorted(set(image_paths))


def predict_image(model: YOLO, image_path: Path) -> list[dict]:
    """Run detection on a single image."""
    results = model.predict(
        source=str(image_path),
        conf=CONF_THRESHOLD,
        iou=IOU_THRESHOLD,
        imgsz=IMG_SIZE,
        max_det=MAX_DETECTIONS,
        verbose=False,
        half=True,
    )

    detections = []
    for result in results:
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            continue

        for i in range(len(boxes)):
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
            detections.append(
                {
                    "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                    "category_id": int(boxes.cls[i].cpu().item()),
                    "score": float(boxes.conf[i].cpu().item()),
                },
            )

    return detections


def parse_image_id(image_path: Path) -> int:
    """Convert img_00042.jpg to the numeric image id 42."""
    return int(image_path.stem.split("_")[1])


def run_inference(images_dir: Path, output_path: Path) -> None:
    """Run inference for all task images and write predictions."""
    image_paths = list_image_paths(images_dir)
    model = load_model(Path(__file__).parent)
    all_detections = []

    with torch.no_grad():
        for image_path in image_paths:
            image_id = parse_image_id(image_path)
            detections = predict_image(model, image_path)
            all_detections.extend(
                {
                    "image_id": image_id,
                    "bbox": det["bbox"],
                    "category_id": det["category_id"],
                    "score": det["score"],
                }
                for det in detections
            )

    with output_path.open("w") as f:
        json.dump(all_detections, f)

    LOGGER.info("Wrote %d detections from %d images", len(all_detections), len(image_paths))


def main() -> None:
    parser = argparse.ArgumentParser(description="Grocery product detection")
    parser.add_argument("--input", type=Path, required=True, help="Input images directory")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON path")
    args = parser.parse_args()
    run_inference(args.input, args.output)


if __name__ == "__main__":
    main()
'''


def read_json(path: Path) -> dict:
    """Read a JSON file into a dict."""
    return json.loads(path.read_text())


def find_best_experiment_dir() -> Path:
    """Pick the experiment with the highest recorded final score."""
    best_experiment_dir: Path | None = None
    best_score = float("-inf")

    for settings_path in EXPERIMENTS_DIR.glob("*/best_settings.json"):
        settings = read_json(settings_path)
        score = float(settings.get("final_score", float("-inf")))
        if score > best_score:
            best_score = score
            best_experiment_dir = settings_path.parent

    if best_experiment_dir is None:
        raise FileNotFoundError(
            "No experiment with best_settings.json found. Train/evaluate an experiment first or set --experiment-dir.",
        )

    return best_experiment_dir


def find_default_weights() -> Path:
    """Resolve the default submission weights."""
    experiment_dir = find_best_experiment_dir()
    weights_path = experiment_dir / "train" / "weights" / "best.pt"
    if weights_path.exists():
        return weights_path

    direct_candidates = [
        RUNS_DIR / "classify" / "weights" / "best.pt",
        RUNS_DIR / "detect" / "weights" / "best.pt",
        TASK_DIR / "weights" / "best.pt",
        TASK_DIR / "weights" / "model.pt",
        TASK_DIR / "weights" / "best.onnx",
        TASK_DIR / "weights" / "model.onnx",
    ]
    for candidate in direct_candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError("No weights found. Train a model first or set --weights.")


def resolve_experiment_dir(
    experiment_dir: Path | None,
    weights_path: Path | None,
) -> Path | None:
    """Resolve which experiment directory should provide tuned settings."""
    if experiment_dir is not None:
        return experiment_dir

    if weights_path is not None:
        train_dir = weights_path.parent.parent
        if train_dir.name == "train" and train_dir.parent.parent == EXPERIMENTS_DIR:
            return train_dir.parent
        return None

    return find_best_experiment_dir()


def resolve_weights_path(weights_path: Path | None, experiment_dir: Path | None) -> Path:
    """Resolve the weights to package."""
    if weights_path is not None:
        return weights_path

    if experiment_dir is not None:
        experiment_weights = experiment_dir / "train" / "weights" / "best.pt"
        if experiment_weights.exists():
            return experiment_weights
        raise FileNotFoundError(f"No best.pt found under {experiment_dir / 'train' / 'weights'}")

    return find_default_weights()


def build_packaged_run_py(best_settings: dict | None, config: dict | None) -> str:
    """Render the packaged inference entry point with tuned settings."""
    conf_threshold = float((best_settings or {}).get("conf", 0.25))
    iou_threshold = float((best_settings or {}).get("iou", 0.45))
    img_size = int((config or {}).get("imgsz", 1280))
    max_detections = int((config or {}).get("max_detections", 300))

    return (
        PACKAGED_RUN_PY_TEMPLATE.replace("__CONF_THRESHOLD__", str(conf_threshold))
        .replace("__IOU_THRESHOLD__", str(iou_threshold))
        .replace("__IMG_SIZE__", str(img_size))
        .replace("__MAX_DETECTIONS__", str(max_detections))
    )


def create_submission_dir(base_dir: Path | None = None) -> Path:
    """Create a timestamped submission directory."""
    root = base_dir or SUBMISSIONS_DIR
    timestamp = datetime.now(UTC).strftime(TIMESTAMP_FORMAT)
    submission_root = root / timestamp
    submission_root.mkdir(parents=True, exist_ok=False)
    return submission_root


def write_submission_tree(
    submission_root: Path,
    weights_path: Path,
    best_settings: dict | None,
    config: dict | None,
) -> tuple[Path, Path]:
    """Create the unpacked submission directory contents."""
    submission_dir = submission_root / "submission"
    submission_dir.mkdir()

    run_py_path = submission_dir / "run.py"
    run_py_path.write_text(build_packaged_run_py(best_settings, config))

    packaged_weights_path = submission_dir / "best.pt"
    shutil.copyfile(weights_path, packaged_weights_path)

    return submission_dir, packaged_weights_path


def create_submission_zip(submission_dir: Path, output_path: Path) -> None:
    """Zip the unpacked submission with identical archive contents."""
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(submission_dir.iterdir()):
            zf.write(file_path, file_path.name)


def package_submission(
    weights_path: Path | None = None,
    experiment_dir: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Create a timestamped submission directory and ZIP."""
    resolved_experiment_dir = resolve_experiment_dir(experiment_dir, weights_path)
    resolved_weights = resolve_weights_path(weights_path, resolved_experiment_dir)
    best_settings = None
    config = None
    if resolved_experiment_dir is not None:
        settings_path = resolved_experiment_dir / "best_settings.json"
        config_path = resolved_experiment_dir / "config.json"
        if settings_path.exists():
            best_settings = read_json(settings_path)
        if config_path.exists():
            config = read_json(config_path)

    submission_root = create_submission_dir(output_dir)
    submission_dir, _ = write_submission_tree(
        submission_root,
        resolved_weights,
        best_settings,
        config,
    )
    zip_path = submission_root / "submission.zip"
    create_submission_zip(submission_dir, zip_path)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    LOGGER.info("Created submission directory: %s", submission_dir)
    LOGGER.info("Created submission zip: %s (%.1f MB)", zip_path, size_mb)

    if size_mb > 420:
        LOGGER.warning("ZIP is %.1f MB, exceeds ~420 MB limit", size_mb)

    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Package submission ZIP")
    parser.add_argument("--weights", type=Path, help="Model weights path")
    parser.add_argument(
        "--experiment-dir",
        type=Path,
        help="Experiment directory with best_settings.json",
    )
    parser.add_argument("--output-dir", type=Path, help="Submission output directory")
    args = parser.parse_args()

    package_submission(
        weights_path=args.weights,
        experiment_dir=args.experiment_dir,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
