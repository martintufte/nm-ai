# Task 3: Norgesgruppen - Grocery Product Detection

## Overview
Detect and classify grocery products on store shelf images.

## Training Data
- **COCO dataset** (~864 MB): 248 shelf images, ~22,700 annotations, 356 product categories
  - Bounding boxes in COCO format: `[x, y, width, height]` in pixels
  - Annotations include `product_code` (barcode) and `corrected` flag
- **Product reference images** (~60 MB): 327 products with multi-angle photos (`{product_code}/main.jpg`)

## Submission
- ZIP file with `run.py` at root + model weights + helper files
- **Max size**: ~420 MB practical limit for weights
- **Execution**: `python run.py --images /data/images/ --output /tmp/output.json`

## Output Format
```json
[
  {
    "image_id": "img_00042",
    "bbox": [x, y, width, height],
    "category_id": 123,
    "score": 0.95
  }
]
```

## Scoring (70/30 split)
- **70% detection mAP**: IoU >= 0.5, category ignored
- **30% classification mAP**: IoU >= 0.5 AND correct `category_id`
- Detection-only submissions (all `category_id: 0`) score up to 70%

## Execution Environment
- **GPU**: NVIDIA L4 (24 GB VRAM)
- **Timeout**: 300 seconds
- **No internet access**
- **Pre-installed**: PyTorch 2.6.0+cu124, torchvision 0.21.0+cu124, ultralytics 8.1.0,
  onnxruntime-gpu 1.20.0, opencv-python-headless 4.9.0.80, albumentations 1.3.1,
  Pillow 10.2.0, numpy 1.26.4, scipy 1.12.0, scikit-learn 1.4.0, pycocotools 2.0.7,
  ensemble-boxes 1.0.9, timm 0.9.12, supervision 0.18.0, safetensors 0.4.2

## Blocked Imports (sandbox security)
`os`, `sys`, `subprocess`, `socket`, `ctypes`, `builtins`, `importlib`, `pickle`,
`marshal`, `shelve`, `shutil`, `yaml`, `requests`, `urllib`, `http.client`,
`multiprocessing`, `threading`, `signal`, `gc`, `code`, `codeop`, `pty`

Use `pathlib` instead of `os`, `json` instead of `yaml`.

## Submission Limits
10 per day (infrastructure errors: first 2/day don't count)
