"""Package submission ZIP for the Norgesgruppen task.

Creates a ZIP file with:
    run.py          - Entry point
    best.pt         - Model weights
    category_map.json - Category ID mapping (if multi-class)

Usage:
    python -m norgesgruppen.package [--weights path/to/best.pt] [--output submission.zip]
"""

import argparse
import json
import logging
import zipfile
from pathlib import Path

LOGGER = logging.getLogger(__name__)

TASK_DIR = Path(__file__).parent
RUNS_DIR = TASK_DIR / "runs"


def package_submission(
    weights_path: Path | None = None,
    output_path: Path | None = None,
    include_category_map: bool = True,
) -> Path:
    """Create submission ZIP.

    Args:
        weights_path: Path to model weights (default: runs/classify/weights/best.pt)
        output_path: Output ZIP path (default: submission.zip in task dir)
        include_category_map: Include category mapping JSON
    """
    if weights_path is None:
        # Try classify first, then detect
        for candidate in [
            RUNS_DIR / "classify" / "weights" / "best.pt",
            RUNS_DIR / "detect" / "weights" / "best.pt",
        ]:
            if candidate.exists():
                weights_path = candidate
                break
        if weights_path is None:
            raise FileNotFoundError("No weights found. Train a model first.")

    if output_path is None:
        output_path = TASK_DIR / "submission.zip"

    run_py = TASK_DIR / "run.py"
    if not run_py.exists():
        raise FileNotFoundError(f"run.py not found at {run_py}")

    LOGGER.info("Packaging submission:")
    LOGGER.info("  run.py:  %s", run_py)
    LOGGER.info("  weights: %s", weights_path)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # run.py must be at root of ZIP
        zf.write(run_py, "run.py")

        # Model weights
        zf.write(weights_path, "best.pt")

        # Category mapping (for debugging / reference)
        if include_category_map:
            cat_map_path = TASK_DIR / "data" / "coco" / "annotations.json"
            if cat_map_path.exists():
                with cat_map_path.open() as f:
                    coco = json.load(f)
                categories = {cat["id"]: cat["name"] for cat in coco.get("categories", [])}
                zf.writestr("category_map.json", json.dumps(categories, indent=2))

    size_mb = output_path.stat().st_size / (1024 * 1024)
    LOGGER.info("Created: %s (%.1f MB)", output_path, size_mb)

    if size_mb > 420:
        LOGGER.warning("ZIP is %.1f MB, exceeds ~420 MB limit!", size_mb)
        LOGGER.warning("Consider using FP16 export or a smaller model.")

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Package submission ZIP")
    parser.add_argument("--weights", type=Path, help="Model weights path")
    parser.add_argument("--output", type=Path, help="Output ZIP path")
    args = parser.parse_args()

    package_submission(weights_path=args.weights, output_path=args.output)


if __name__ == "__main__":
    main()
