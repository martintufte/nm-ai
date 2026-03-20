"""Convert COCO annotations to YOLO format for ultralytics training.

Usage:
    python -m nmai.tasks.norgesgruppen.data.convert [--single-class]

Creates a YOLO dataset structure:
    data/yolo/
    ├── dataset.yaml
    ├── train/
    │   ├── images/  (symlinks)
    │   └── labels/  (txt files)
    └── val/
        ├── images/  (symlinks)
        └── labels/  (txt files)
"""

import argparse
import json
import logging
import random
from collections import defaultdict
from pathlib import Path

from norgesgruppen.data.load import COCO_DIR

LOGGER = logging.getLogger(__name__)

YOLO_DIR = Path(__file__).parent / "yolo"


def coco_to_yolo_bbox(
    bbox: list[float],
    img_w: int,
    img_h: int,
) -> tuple[float, float, float, float]:
    """Convert COCO bbox [x, y, w, h] (pixels) to YOLO [cx, cy, w, h] (normalized)."""
    x, y, w, h = bbox
    cx = (x + w / 2) / img_w
    cy = (y + h / 2) / img_h
    nw = w / img_w
    nh = h / img_h
    return (
        max(0.0, min(1.0, cx)),
        max(0.0, min(1.0, cy)),
        max(0.0, min(1.0, nw)),
        max(0.0, min(1.0, nh)),
    )


def convert_coco_to_yolo(
    val_fraction: float = 0.15,
    single_class: bool = False,
    seed: int = 42,
) -> Path:
    """Convert COCO dataset to YOLO format.

    Args:
        val_fraction: Fraction of images for validation.
        single_class: If True, all objects get class 0 (detection-only mode).
        seed: Random seed for train/val split.

    Returns:
        Path to generated dataset.yaml
    """
    annotations_path = COCO_DIR / "train" / "annotations.json"
    images_dir = COCO_DIR / "train" / "images"

    with annotations_path.open() as f:
        coco = json.load(f)

    # Build lookups
    images_by_id = {img["id"]: img for img in coco["images"]}
    annotations_by_image: dict[int, list] = defaultdict(list)
    for ann in coco["annotations"]:
        annotations_by_image[ann["image_id"]].append(ann)

    categories = coco.get("categories", [])
    if single_class:
        num_classes = 1
        class_names = ["product"]
    else:
        num_classes = len(categories)
        cat_id_to_idx = {cat["id"]: idx for idx, cat in enumerate(categories)}
        class_names = [cat["name"] for cat in categories]

    # Train/val split
    image_ids = sorted(images_by_id.keys())
    random.seed(seed)
    random.shuffle(image_ids)
    val_count = max(1, int(len(image_ids) * val_fraction))
    val_ids = set(image_ids[:val_count])
    train_ids = set(image_ids[val_count:])

    # Create directory structure
    for split in ["train", "val"]:
        (YOLO_DIR / split / "images").mkdir(parents=True, exist_ok=True)
        (YOLO_DIR / split / "labels").mkdir(parents=True, exist_ok=True)

    # Write labels and symlink images
    for img_id, img_info in images_by_id.items():
        split = "val" if img_id in val_ids else "train"
        img_w = img_info["width"]
        img_h = img_info["height"]
        img_filename = img_info["file_name"]
        stem = Path(img_filename).stem

        # Symlink image
        src = (images_dir / img_filename).resolve()
        dst = YOLO_DIR / split / "images" / img_filename
        if not dst.exists() and src.exists():
            dst.symlink_to(src)

        # Write YOLO label
        label_path = YOLO_DIR / split / "labels" / f"{stem}.txt"
        lines = []
        for ann in annotations_by_image.get(img_id, []):
            cx, cy, nw, nh = coco_to_yolo_bbox(ann["bbox"], img_w, img_h)
            cls_idx = 0 if single_class else cat_id_to_idx.get(ann["category_id"], 0)
            lines.append(f"{cls_idx} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        label_path.write_text("\n".join(lines) + "\n" if lines else "")

    # Write dataset.yaml
    yaml_path = YOLO_DIR / "dataset.yaml"
    yaml_content = (
        f"path: {YOLO_DIR.resolve()}\n"
        f"train: train/images\n"
        f"val: val/images\n"
        f"nc: {num_classes}\n"
        f"names: {class_names}\n"
    )
    yaml_path.write_text(yaml_content)

    LOGGER.info("YOLO dataset created at %s", YOLO_DIR)
    LOGGER.info("  Train: %d images", len(train_ids))
    LOGGER.info("  Val:   %d images", len(val_ids))
    LOGGER.info(
        "  Classes: %d (%s)",
        num_classes,
        "single-class" if single_class else "multi-class",
    )

    return yaml_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert COCO to YOLO format")
    parser.add_argument(
        "--single-class",
        action="store_true",
        help="Detection-only (all class 0)",
    )
    parser.add_argument(
        "--val-fraction",
        type=float,
        default=0.15,
        help="Validation split fraction",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for split")
    args = parser.parse_args()

    convert_coco_to_yolo(
        val_fraction=args.val_fraction,
        single_class=args.single_class,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
