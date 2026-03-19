"""Data loading for Norgesgruppen grocery detection task.

Usage:
    from nmai.tasks.norgesgruppen.data.load import (
        load_coco_annotations,
        load_product_references,
        get_category_mapping,
        get_annotation_stats,
    )
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent
COCO_DIR = DATA_DIR / "coco"
REFERENCE_DIR = DATA_DIR / "product_references"


def load_coco_annotations(annotations_path: Path | None = None) -> dict:
    """Load COCO format annotations.

    Returns dict with keys: 'images', 'annotations', 'categories'.

    Each annotation has:
        - id: int
        - image_id: int
        - bbox: [x, y, width, height] in pixels
        - category_id: int (0-355)
        - product_code: str (barcode)
        - corrected: bool (manually verified)
    """
    if annotations_path is None:
        annotations_path = COCO_DIR / "annotations.json"

    with open(annotations_path) as f:
        return json.load(f)


def get_image_paths(images_dir: Path | None = None) -> list[Path]:
    """Get all training image paths sorted by name."""
    if images_dir is None:
        images_dir = COCO_DIR / "images"
    return sorted(images_dir.glob("*.jpg"))


def get_category_mapping(annotations: dict) -> dict[int, str]:
    """Extract category_id -> category_name mapping from COCO annotations."""
    return {cat["id"]: cat["name"] for cat in annotations.get("categories", [])}


def get_annotation_stats(annotations: dict) -> dict:
    """Compute summary statistics for the dataset."""
    annots = annotations.get("annotations", [])
    images = annotations.get("images", [])
    categories = annotations.get("categories", [])

    # Annotations per image
    from collections import Counter
    img_counts = Counter(a["image_id"] for a in annots)
    cat_counts = Counter(a["category_id"] for a in annots)

    return {
        "num_images": len(images),
        "num_annotations": len(annots),
        "num_categories": len(categories),
        "annotations_per_image": {
            "mean": sum(img_counts.values()) / max(len(img_counts), 1),
            "min": min(img_counts.values()) if img_counts else 0,
            "max": max(img_counts.values()) if img_counts else 0,
        },
        "annotations_per_category": {
            "mean": sum(cat_counts.values()) / max(len(cat_counts), 1),
            "min": min(cat_counts.values()) if cat_counts else 0,
            "max": max(cat_counts.values()) if cat_counts else 0,
        },
    }


def load_product_references(reference_dir: Path | None = None) -> dict[str, list[Path]]:
    """Load product reference images organized by barcode.

    Returns:
        Dict mapping product_code -> list of reference image paths.
    """
    if reference_dir is None:
        reference_dir = REFERENCE_DIR

    products: dict[str, list[Path]] = {}
    if not reference_dir.exists():
        return products

    for product_dir in sorted(reference_dir.iterdir()):
        if product_dir.is_dir():
            product_code = product_dir.name
            images = sorted(product_dir.glob("*.jpg")) + sorted(product_dir.glob("*.png"))
            if images:
                products[product_code] = images

    return products


def build_product_code_to_category(annotations: dict) -> dict[str, int]:
    """Build mapping from product_code to category_id using annotations."""
    mapping: dict[str, int] = {}
    for ann in annotations.get("annotations", []):
        pc = ann.get("product_code")
        if pc and pc not in mapping:
            mapping[pc] = ann["category_id"]
    return mapping
