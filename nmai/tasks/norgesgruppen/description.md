# Task 3: Norgesgruppen - Grocery Product Detection

## Overview
Detect and classify grocery products on store shelf images.

## Training Data
- **COCO dataset** (~864 MB): 248 shelf images, ~22,700 annotations, 356 product categories
  - Bounding boxes in COCO format: `[x, y, width, height]` in pixels
- **Product reference images** (~60 MB): 327 products with multi-angle photos organized by barcode

## Submission
- ZIP file with `run.py` at root + model weights + helper files
- **Max size**: 420 MB
- **Execution**: `python run.py --images /data/images/ --output /output.json`

## Input
JPEG images in `/data/images/` (format: `img_XXXXX.jpg`)

## Output Format
```json
[
  {
    "image_id": "img_00042",
    "bbox": [x, y, w, h],
    "category_id": 0,
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
  onnxruntime-gpu 1.20.0, opencv-python-headless, albumentations, Pillow, numpy, scipy,
  scikit-learn, pycocotools, ensemble-boxes, timm, supervision, safetensors
- **NOT available**: YOLOv9/10/11, Detectron2, MMDetection (export to ONNX or bundle code)
- **Security**: Blocks `os`, `subprocess`, `socket`, `eval()`, `exec()`, ELF binaries, path traversal

## Submission Limits
10 per day (infrastructure errors: first 2/day don't count)

## Tips
- Start with random baseline to verify setup
- Use FP16 quantization to fit within VRAM
- Process images one-by-one with `torch.no_grad()`
- Verify ZIP structure with `unzip -l`
