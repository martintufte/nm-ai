"""Explore and visualize the Norgesgruppen dataset.

Usage:
    python -m nmai.tasks.norgesgruppen.data.explore
"""

from collections import Counter
from pathlib import Path

from nmai.tasks.norgesgruppen.data.load import (
    load_coco_annotations,
    get_annotation_stats,
    get_category_mapping,
    get_image_paths,
    load_product_references,
    build_product_code_to_category,
)


def explore() -> None:
    """Print dataset statistics."""
    annotations = load_coco_annotations()
    stats = get_annotation_stats(annotations)

    print("=" * 60)
    print("NORGESGRUPPEN DATASET OVERVIEW")
    print("=" * 60)

    print(f"\nImages:      {stats['num_images']}")
    print(f"Annotations: {stats['num_annotations']}")
    print(f"Categories:  {stats['num_categories']}")

    print(f"\nAnnotations per image:")
    print(f"  Mean: {stats['annotations_per_image']['mean']:.1f}")
    print(f"  Min:  {stats['annotations_per_image']['min']}")
    print(f"  Max:  {stats['annotations_per_image']['max']}")

    print(f"\nAnnotations per category:")
    print(f"  Mean: {stats['annotations_per_category']['mean']:.1f}")
    print(f"  Min:  {stats['annotations_per_category']['min']}")
    print(f"  Max:  {stats['annotations_per_category']['max']}")

    # Category distribution
    categories = get_category_mapping(annotations)
    cat_counts = Counter(a["category_id"] for a in annotations["annotations"])
    print(f"\nTop 10 categories:")
    for cat_id, count in cat_counts.most_common(10):
        name = categories.get(cat_id, f"unknown_{cat_id}")
        print(f"  {cat_id:>4d}: {name:<40s} ({count} annotations)")

    print(f"\nBottom 10 categories:")
    for cat_id, count in cat_counts.most_common()[-10:]:
        name = categories.get(cat_id, f"unknown_{cat_id}")
        print(f"  {cat_id:>4d}: {name:<40s} ({count} annotations)")

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
    print(f"\nBbox relative area (fraction of image):")
    print(f"  Median: {areas[n // 2]:.5f}")
    print(f"  P10:    {areas[n // 10]:.5f}")
    print(f"  P90:    {areas[9 * n // 10]:.5f}")
    print(f"  Min:    {areas[0]:.5f}")
    print(f"  Max:    {areas[-1]:.5f}")

    # Check product references
    refs = load_product_references()
    pc_to_cat = build_product_code_to_category(annotations)
    print(f"\nProduct references: {len(refs)} products")
    print(f"Product codes in annotations: {len(pc_to_cat)}")
    overlap = set(refs.keys()) & set(pc_to_cat.keys())
    print(f"Overlap (refs ∩ annotations): {len(overlap)}")

    # Image sizes
    image_paths = get_image_paths()
    if image_paths:
        from PIL import Image
        sizes = set()
        for p in image_paths[:10]:
            img = Image.open(p)
            sizes.add(img.size)
        print(f"\nSample image sizes: {sizes}")


if __name__ == "__main__":
    explore()
