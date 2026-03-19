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
from pathlib import Path

import torch
from ultralytics import YOLO


# Confidence and NMS thresholds -- tune these on validation set
CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45
IMG_SIZE = 1280
MAX_DETECTIONS = 300


def load_model(weights_dir: Path) -> YOLO:
    """Load YOLOv8 model from weights in the submission directory."""
    # Try different weight formats in priority order
    for name in ["best.pt", "model.pt", "best.onnx", "model.onnx"]:
        weights_path = weights_dir / name
        if weights_path.exists():
            print(f"Loading model from {weights_path}")
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

            detections.append({
                "bbox": [float(x1), float(y1), w, h],
                "category_id": int(boxes.cls[i].cpu().item()),
                "score": float(boxes.conf[i].cpu().item()),
            })

    return detections


def run_inference(images_dir: Path, output_path: Path) -> None:
    """Run inference on all test images and write results."""
    weights_dir = Path(__file__).parent

    # Load model
    model = load_model(weights_dir)

    # Get all test images
    image_paths = sorted(images_dir.glob("img_*.jpg"))
    print(f"Found {len(image_paths)} images")

    all_detections = []

    with torch.no_grad():
        for idx, img_path in enumerate(image_paths):
            image_id = img_path.stem

            detections = predict_image(model, img_path)

            for det in detections:
                all_detections.append(
                    {
                        "image_id": image_id,
                        "bbox": det["bbox"],
                        "category_id": det["category_id"],
                        "score": det["score"],
                    }
                )

            if (idx + 1) % 10 == 0:
                print(f"  Processed {idx + 1}/{len(image_paths)} images "
                      f"({len(all_detections)} detections so far)")

    # Write output
    with open(output_path, "w") as f:
        json.dump(all_detections, f)

    print(f"Done: {len(all_detections)} detections from {len(image_paths)} images")


def main() -> None:
    parser = argparse.ArgumentParser(description="Grocery product detection")
    parser.add_argument(
        "--images", type=Path, required=True, help="Input images directory"
    )
    parser.add_argument("--output", type=Path, required=True, help="Output JSON path")
    args = parser.parse_args()

    run_inference(args.images, args.output)


if __name__ == "__main__":
    main()
