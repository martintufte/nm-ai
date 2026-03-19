"""Local evaluation script that mimics the competition scoring.

Scoring: 70% detection mAP (IoU>=0.5, ignore class) + 30% classification mAP (IoU>=0.5 + correct class)

Usage:
    python -m nmai.tasks.norgesgruppen.evaluate --predictions output.json --annotations data/coco/annotations.json
"""

import argparse
import json
from pathlib import Path
from collections import defaultdict

import numpy as np


def compute_iou(box1: list[float], box2: list[float]) -> float:
    """Compute IoU between two [x, y, w, h] boxes."""
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    xi1 = max(x1, x2)
    yi1 = max(y1, y2)
    xi2 = min(x1 + w1, x2 + w2)
    yi2 = min(y1 + h1, y2 + h2)

    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    union = w1 * h1 + w2 * h2 - inter

    return inter / union if union > 0 else 0.0


def compute_ap(precisions: list[float], recalls: list[float]) -> float:
    """Compute Average Precision using 101-point interpolation (COCO style)."""
    if not precisions:
        return 0.0

    # Add sentinel values
    precisions = [0.0] + precisions + [0.0]
    recalls = [0.0] + recalls + [1.0]

    # Make precision monotonically decreasing
    for i in range(len(precisions) - 2, -1, -1):
        precisions[i] = max(precisions[i], precisions[i + 1])

    # 101-point interpolation
    ap = 0.0
    for t in np.linspace(0, 1, 101):
        p = 0.0
        for r, pr in zip(recalls, precisions):
            if r >= t:
                p = max(p, pr)
        ap += p
    return ap / 101


def evaluate_map(
    predictions: list[dict],
    ground_truth: dict,
    iou_threshold: float = 0.5,
    ignore_class: bool = False,
) -> float:
    """Compute mAP at given IoU threshold.

    Args:
        predictions: List of {image_id, bbox, category_id, score}
        ground_truth: COCO format annotations dict
        iou_threshold: IoU threshold for matching
        ignore_class: If True, only evaluate detection (ignore category)

    Returns:
        mAP score
    """
    # Build GT lookup: image_filename -> list of annotations
    images_by_id = {img["id"]: img for img in ground_truth["images"]}
    gt_by_image: dict[str, list[dict]] = defaultdict(list)
    for ann in ground_truth["annotations"]:
        img = images_by_id.get(ann["image_id"])
        if img:
            image_id = Path(img["file_name"]).stem
            gt_by_image[image_id].append(ann)

    # Get all unique categories
    if ignore_class:
        categories = [0]  # single "any" class
    else:
        categories = sorted({ann["category_id"] for ann in ground_truth["annotations"]})

    # Sort predictions by score (descending)
    predictions = sorted(predictions, key=lambda x: x["score"], reverse=True)

    # Group predictions by category
    preds_by_cat: dict[int, list[dict]] = defaultdict(list)
    for pred in predictions:
        cat = 0 if ignore_class else pred["category_id"]
        preds_by_cat[cat].append(pred)

    aps = []
    for cat in categories:
        cat_preds = preds_by_cat.get(cat, [])

        # Count total GT for this category
        total_gt = 0
        gt_matched: dict[str, list[bool]] = {}
        for img_id, gt_anns in gt_by_image.items():
            cat_gt = (
                gt_anns
                if ignore_class
                else [a for a in gt_anns if a["category_id"] == cat]
            )
            total_gt += len(cat_gt)
            gt_matched[img_id] = [False] * len(cat_gt)

        if total_gt == 0:
            continue

        # Match predictions to GT
        tp_list = []
        for pred in cat_preds:
            img_id = pred["image_id"]
            gt_anns = gt_by_image.get(img_id, [])
            cat_gt = (
                gt_anns
                if ignore_class
                else [a for a in gt_anns if a["category_id"] == cat]
            )

            best_iou = 0.0
            best_idx = -1
            for j, gt_ann in enumerate(cat_gt):
                iou = compute_iou(pred["bbox"], gt_ann["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_idx = j

            matched_flags = gt_matched.get(img_id, [])
            # Filter to only category-specific indices
            if not ignore_class:
                cat_indices = [
                    i for i, a in enumerate(gt_anns) if a["category_id"] == cat
                ]
                if best_idx >= 0 and best_idx < len(cat_indices):
                    global_idx = cat_indices[best_idx]
                else:
                    global_idx = -1
            else:
                global_idx = best_idx

            if (
                best_iou >= iou_threshold
                and global_idx >= 0
                and not matched_flags[best_idx]
            ):
                tp_list.append(1)
                matched_flags[best_idx] = True
            else:
                tp_list.append(0)

        # Compute precision/recall curve
        tp_cumsum = np.cumsum(tp_list)
        fp_cumsum = np.arange(1, len(tp_list) + 1) - tp_cumsum

        precisions = (tp_cumsum / (tp_cumsum + fp_cumsum)).tolist()
        recalls = (tp_cumsum / total_gt).tolist()

        ap = compute_ap(precisions, recalls)
        aps.append(ap)

    return float(np.mean(aps)) if aps else 0.0


def evaluate(predictions_path: Path, annotations_path: Path) -> None:
    """Run full evaluation matching competition scoring."""
    with open(predictions_path) as f:
        predictions = json.load(f)
    with open(annotations_path) as f:
        ground_truth = json.load(f)

    print(f"Predictions: {len(predictions)}")
    print(f"Ground truth images: {len(ground_truth['images'])}")
    print(f"Ground truth annotations: {len(ground_truth['annotations'])}")
    print()

    detection_map = evaluate_map(predictions, ground_truth, ignore_class=True)
    classification_map = evaluate_map(predictions, ground_truth, ignore_class=False)

    final_score = 0.7 * detection_map + 0.3 * classification_map

    print(f"Detection mAP@0.5:       {detection_map:.4f}  (weight: 70%)")
    print(f"Classification mAP@0.5:  {classification_map:.4f}  (weight: 30%)")
    print(f"Final score:             {final_score:.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate predictions")
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    args = parser.parse_args()

    evaluate(args.predictions, args.annotations)


if __name__ == "__main__":
    main()
