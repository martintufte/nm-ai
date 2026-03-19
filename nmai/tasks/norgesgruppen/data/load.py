"""Data loading for Norgesgruppen grocery detection task.

Downloads and loads the COCO training dataset and product reference images.

Usage:
    from nmai.tasks.norgesgruppen.data.load import load_coco_annotations, load_product_references

    annotations = load_coco_annotations()
    references = load_product_references()
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
        - image_id: int
        - bbox: [x, y, width, height] in pixels
        - category_id: int (0-355)
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


def load_product_references(reference_dir: Path | None = None) -> dict[str, list[Path]]:
    """Load product reference images organized by barcode.

    Returns:
        Dict mapping barcode -> list of reference image paths.
    """
    if reference_dir is None:
        reference_dir = REFERENCE_DIR

    products: dict[str, list[Path]] = {}
    if not reference_dir.exists():
        return products

    for product_dir in sorted(reference_dir.iterdir()):
        if product_dir.is_dir():
            barcode = product_dir.name
            images = sorted(product_dir.glob("*.jpg")) + sorted(product_dir.glob("*.png"))
            if images:
                products[barcode] = images

    return products
