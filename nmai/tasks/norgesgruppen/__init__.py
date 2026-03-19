"""Task 3: Norgesgruppen - Grocery Product Detection

Detect and classify grocery products on store shelf images.

Pipeline:
    1. Download data: Place COCO dataset in data/coco/, product refs in data/product_references/
    2. Explore:       python -m nmai.tasks.norgesgruppen.data.explore
    3. Convert:       python -m nmai.tasks.norgesgruppen.data.convert [--single-class]
    4. Train:         python -m nmai.tasks.norgesgruppen.train --mode detect
    5. Evaluate:      python -m nmai.tasks.norgesgruppen.evaluate --predictions out.json --annotations data/coco/annotations.json
    6. Package:       python -m nmai.tasks.norgesgruppen.package
"""
