"""Explore and visualize the NorgesGruppen dataset.

Usage:
    python -m norgesgruppen.data.explore
"""

import logging
from collections import Counter

from PIL import Image

from norgesgruppen.data.load import build_product_code_to_category
from norgesgruppen.data.load import get_annotation_stats
from norgesgruppen.data.load import get_category_mapping
from norgesgruppen.data.load import get_image_paths
from norgesgruppen.data.load import load_coco_annotations
from norgesgruppen.data.load import load_product_references

LOGGER = logging.getLogger(__name__)


def explore() -> None:
    """Print dataset statistics."""
    annotations = load_coco_annotations()
    stats = get_annotation_stats(annotations)

    LOGGER.info("=" * 60)
    LOGGER.info("NORGESGRUPPEN DATASET OVERVIEW")
    LOGGER.info("=" * 60)

    LOGGER.info("Images:      %d", stats["num_images"])
    LOGGER.info("Annotations: %d", stats["num_annotations"])
    LOGGER.info("Categories:  %d", stats["num_categories"])

    LOGGER.info("Annotations per image:")
    LOGGER.info("  Mean: %.1f", stats["annotations_per_image"]["mean"])
    LOGGER.info("  Min:  %d", stats["annotations_per_image"]["min"])
    LOGGER.info("  Max:  %d", stats["annotations_per_image"]["max"])

    LOGGER.info("Annotations per category:")
    LOGGER.info("  Mean: %.1f", stats["annotations_per_category"]["mean"])
    LOGGER.info("  Min:  %d", stats["annotations_per_category"]["min"])
    LOGGER.info("  Max:  %d", stats["annotations_per_category"]["max"])

    # Category distribution
    categories = get_category_mapping(annotations)
    cat_counts = Counter(a["category_id"] for a in annotations["annotations"])
    LOGGER.info("Top 10 categories:")
    for cat_id, count in cat_counts.most_common(10):
        name = categories.get(cat_id, f"unknown_{cat_id}")
        LOGGER.info("  %4d: %-40s (%d annotations)", cat_id, name, count)

    LOGGER.info("Bottom 10 categories:")
    for cat_id, count in cat_counts.most_common()[-10:]:
        name = categories.get(cat_id, f"unknown_{cat_id}")
        LOGGER.info("  %4d: %-40s (%d annotations)", cat_id, name, count)

    # Bbox size distribution
    annots = annotations["annotations"]
    images_by_id = {img["id"]: img for img in annotations["images"]}
    areas = []
    for a in annots:
        w, h = a["bbox"][2], a["bbox"][3]
        img = images_by_id.get(a["image_id"], {})
        iw = img.get("width", 1)
        ih = img.get("height", 1)
        rel_area = (w * h) / (iw * ih)
        areas.append(rel_area)

    areas.sort()
    n = len(areas)
    LOGGER.info("Bbox relative area (fraction of image):")
    LOGGER.info("  Median: %.5f", areas[n // 2])
    LOGGER.info("  P10:    %.5f", areas[n // 10])
    LOGGER.info("  P90:    %.5f", areas[9 * n // 10])
    LOGGER.info("  Min:    %.5f", areas[0])
    LOGGER.info("  Max:    %.5f", areas[-1])

    # Check product references
    refs = load_product_references()
    pc_to_cat = build_product_code_to_category(annotations)
    LOGGER.info("Product references: %d products", len(refs))
    LOGGER.info("Product codes in annotations: %d", len(pc_to_cat))
    overlap = set(refs.keys()) & set(pc_to_cat.keys())
    LOGGER.info("Overlap (refs ∩ annotations): %d", len(overlap))

    # Image sizes
    image_paths = get_image_paths()
    if image_paths:
        sizes = set()
        for p in image_paths[:10]:
            img = Image.open(p)
            sizes.add(img.size)
        LOGGER.info("Sample image sizes: %s", sizes)


if __name__ == "__main__":
    explore()
