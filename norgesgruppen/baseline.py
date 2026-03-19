"""Generate a random baseline prediction file for local scoring."""

import argparse
import json
from pathlib import Path

import numpy as np

from norgesgruppen.evaluate import evaluate
from norgesgruppen.run_utils import copy_predictions
from norgesgruppen.run_utils import create_run_dir


def generate_random_predictions(
    annotations: dict,
    seed: int = 0,
    max_dets_per_image: int = 100,
) -> list[dict]:
    rng = np.random.default_rng(seed)

    categories = sorted({ann["category_id"] for ann in annotations["annotations"]})
    if not categories:
        return []

    predictions: list[dict] = []
    for img in annotations["images"]:
        image_id = Path(img["file_name"]).stem
        width = int(img["width"])
        height = int(img["height"])

        num_dets = int(rng.integers(1, max_dets_per_image + 1))
        for _ in range(num_dets):
            max_box_width = max(1, width // 5)
            max_box_height = max(1, height // 5)
            box_width = int(rng.integers(1, max_box_width + 1))
            box_height = int(rng.integers(1, max_box_height + 1))
            x = int(rng.integers(0, width - box_width + 1))
            y = int(rng.integers(0, height - box_height + 1))

            predictions.append(
                {
                    "image_id": image_id,
                    "bbox": [x, y, box_width, box_height],
                    "category_id": int(rng.choice(categories)),
                    "score": float(rng.uniform(0.01, 1.0)),
                },
            )

    return predictions


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate random baseline predictions")
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-dets-per-image", type=int, default=10)
    args = parser.parse_args()

    with args.annotations.open() as f:
        annotations = json.load(f)

    predictions = generate_random_predictions(
        annotations,
        seed=args.seed,
        max_dets_per_image=args.max_dets_per_image,
    )

    with args.output.open("w") as f:
        json.dump(predictions, f)

    run_dir = create_run_dir("baseline")
    (run_dir / "model_weights").mkdir(parents=True, exist_ok=True)
    predictions_path = copy_predictions(args.output, run_dir)
    evaluate(predictions_path, args.annotations)


if __name__ == "__main__":
    main()
