"""Norgesgruppen grocery product detection - Submission entry point.

This file runs in the sandboxed competition environment:
    python run.py --images /data/images/ --output /tmp/output.json

IMPORTANT sandbox constraints:
    - Cannot import: os, sys, subprocess, socket, shutil, yaml, requests, etc.
    - Must use pathlib instead of os
    - Must use json instead of yaml
    - GPU: NVIDIA L4 (24 GB VRAM), timeout: 300 seconds
    - ultralytics 8.1.0 is pre-installed
"""

import argparse
import json
import logging
from pathlib import Path

import torch
from ultralytics import YOLO

from norgesgruppen.evaluate import evaluate
from norgesgruppen.run_utils import copy_predictions
from norgesgruppen.run_utils import copy_weights
from norgesgruppen.run_utils import create_run_dir

LOGGER = logging.getLogger(__name__)

# Confidence and NMS thresholds -- tune these on validation set
CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45
IMG_SIZE = 1280
MAX_DETECTIONS = 300


def infer_annotations_path(images_dir: Path) -> Path | None:
    """Infer a local COCO annotations path from the images directory."""
    candidate = images_dir.parent / "annotations.json"
    if candidate.exists():
        return candidate
    return None


def finalize_local_run(
    output_path: Path,
    run_dir: Path,
    annotations_path: Path | None,
) -> None:
    """Persist predictions and optionally calculate a local score."""
    copied_predictions = copy_predictions(output_path, run_dir)
    if annotations_path is not None:
        evaluate(copied_predictions, annotations_path)


def load_model(weights_dir: Path) -> YOLO:
    """Load YOLOv8 model from weights in the submission directory."""
    # Try different weight formats in priority order
    for name in ["best.pt", "model.pt", "best.onnx", "model.onnx"]:
        weights_path = weights_dir / name
        if weights_path.exists():
            LOGGER.info("Loading model from %s", weights_path)
            model = YOLO(str(weights_path))
            model.fuse()
            return model

    raise FileNotFoundError(f"No model weights found in {weights_dir}")


def predict_image(model: YOLO, image_path: Path) -> list[dict]:
    """Run detection on a single image, return list of detections."""
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
            # xyxy -> xywh (COCO format)
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
            w = float(x2 - x1)
            h = float(y2 - y1)

            detections.append(
                {
                    "bbox": [float(x1), float(y1), w, h],
                    "category_id": int(boxes.cls[i].cpu().item()),
                    "score": float(boxes.conf[i].cpu().item()),
                },
            )

    return detections


def run_inference(images_dir: Path, output_path: Path) -> None:
    """Run inference on all test images and write results."""
    weights_dir = Path(__file__).parent

    # Get all test images
    image_paths = sorted(images_dir.glob("img_*.jpg"))
    LOGGER.info("Found %d images", len(image_paths))

    all_detections = []

    # Load model (unless dummy mode)
    model = load_model(weights_dir)

    with torch.no_grad():
        for idx, img_path in enumerate(image_paths):
            image_id = img_path.stem

            detections = predict_image(model, img_path)

            all_detections.extend(
                [
                    {
                        "image_id": image_id,
                        "bbox": det["bbox"],
                        "category_id": det["category_id"],
                        "score": det["score"],
                    }
                    for det in detections
                ],
            )

            if (idx + 1) % 10 == 0:
                LOGGER.info(
                    "  Processed %d/%d images (%d detections so far)",
                    idx + 1,
                    len(image_paths),
                    len(all_detections),
                )

    # Write output
    with output_path.open("w") as f:
        json.dump(all_detections, f)

    run_dir = create_run_dir("run")
    copy_weights(weights_dir, run_dir / "model_weights")
    finalize_local_run(
        output_path=output_path,
        run_dir=run_dir,
        annotations_path=infer_annotations_path(images_dir),
    )

    LOGGER.info(
        "Done: %d detections from %d images",
        len(all_detections),
        len(image_paths),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Grocery product detection")
    parser.add_argument(
        "--images",
        type=Path,
        required=True,
        help="Input images directory",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output JSON path")
    parser.add_argument(
        "--dummy",
        action="store_true",
        help="Write an empty prediction file without loading model weights",
    )
    args = parser.parse_args()

    if args.dummy:
        args.output.write_text("[]")
        run_dir = create_run_dir("run_dummy")
        (run_dir / "model_weights").mkdir(parents=True, exist_ok=True)
        finalize_local_run(
            output_path=args.output,
            run_dir=run_dir,
            annotations_path=infer_annotations_path(args.images),
        )
        LOGGER.info("Dummy mode: wrote empty predictions to %s", args.output)
        return

    run_inference(args.images, args.output)


if __name__ == "__main__":
    main()
