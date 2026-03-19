"""Task 3: Norgesgruppen - Grocery Product Detection.

Detect and classify grocery products on store shelf images.

Pipeline:
    1. Download data: Place COCO dataset in data/coco/, product refs in data/product_references/
    2. Explore:       python -m norgesgruppen.data.explore
    3. Convert:       python -m norgesgruppen.data.convert [--single-class]
    4. Train:         python -m norgesgruppen.train --mode detect
    5. Evaluate:      python -m norgesgruppen.evaluate --predictions out.json --annotations data/coco/annotations.json
    6. Package:       python -m norgesgruppen.package
"""
