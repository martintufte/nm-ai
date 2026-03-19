"""Training script for Norgesgruppen grocery product detection.

Run locally to train your model, then bundle weights into the submission ZIP.

Usage:
    python -m nmai.tasks.norgesgruppen.train
"""

from nmai.tasks.norgesgruppen.data.load import (
    load_coco_annotations,
    get_image_paths,
    get_category_mapping,
    load_product_references,
)


def train() -> None:
    """Train the detection model.

    TODO: Implement training pipeline.

    Suggested approach:
    1. Load COCO annotations and images
    2. Split into train/val
    3. Fine-tune a pre-trained detector (YOLOv8, Faster R-CNN, etc.)
    4. Export weights in a format compatible with run.py
    5. Ensure total ZIP size < 420 MB (use FP16 quantization)
    """
    # Load data
    annotations = load_coco_annotations()
    image_paths = get_image_paths()
    categories = get_category_mapping(annotations)
    references = load_product_references()

    print(f"Images: {len(image_paths)}")
    print(f"Annotations: {len(annotations.get('annotations', []))}")
    print(f"Categories: {len(categories)}")
    print(f"Reference products: {len(references)}")

    raise NotImplementedError("Implement training pipeline")


if __name__ == "__main__":
    train()
