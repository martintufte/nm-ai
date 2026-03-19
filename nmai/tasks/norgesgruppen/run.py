"""Norgesgruppen grocery product detection - Submission entry point.

This is the file that gets executed in the competition environment:
    python run.py --images /data/images/ --output /output.json

Environment:
    - GPU: NVIDIA L4 (24 GB VRAM)
    - Timeout: 300 seconds
    - No internet access
    - Pre-installed: PyTorch 2.6.0+cu124, torchvision, ultralytics 8.1.0, etc.
    - Security: Blocks os, subprocess, socket, eval(), exec()
"""

import argparse
import json
from pathlib import Path

import torch
from PIL import Image


def load_model(weights_dir: Path) -> object:
    """Load the detection model.

    TODO: Implement model loading.
    Options:
    - ultralytics YOLOv8 (pre-installed)
    - Custom torchvision Faster R-CNN
    - ONNX model via onnxruntime-gpu
    - timm backbone + custom head
    """
    raise NotImplementedError("Implement model loading")


def detect_products(
    model: object,
    image: Image.Image,
) -> list[dict]:
    """Run detection on a single image.

    Returns list of detections, each with:
        - bbox: [x, y, width, height]
        - category_id: int
        - score: float
    """
    raise NotImplementedError("Implement detection logic")


def run_inference(images_dir: Path, output_path: Path) -> None:
    """Run inference on all images and write results."""
    weights_dir = Path(__file__).parent

    # Load model
    model = load_model(weights_dir)

    # Get all test images
    image_paths = sorted(images_dir.glob("img_*.jpg"))
    print(f"Found {len(image_paths)} images")

    all_detections = []

    with torch.no_grad():
        for img_path in image_paths:
            image_id = img_path.stem  # e.g., "img_00042"
            image = Image.open(img_path).convert("RGB")

            detections = detect_products(model, image)

            for det in detections:
                all_detections.append(
                    {
                        "image_id": image_id,
                        "bbox": det["bbox"],
                        "category_id": det["category_id"],
                        "score": det["score"],
                    }
                )

    # Write output
    with open(output_path, "w") as f:
        json.dump(all_detections, f)

    print(f"Wrote {len(all_detections)} detections to {output_path}")


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
