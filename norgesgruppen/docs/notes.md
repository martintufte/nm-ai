# Notes

## Phase 1: Initial sweep of model sizes (1 class)

```bash
uv run python -m norgesgruppen.experiment train --name detect_v8n_1280 --model-size n --epochs 100 --imgsz 1280 --batch -1 --patience 20
uv run python -m norgesgruppen.experiment train --name detect_v8s_1280 --model-size s --epochs 100 --imgsz 1280 --batch -1 --patience 20
uv run python -m norgesgruppen.experiment train --name detect_v8m_1280 --model-size m --epochs 100 --imgsz 1280 --batch -1 --patience 20
# uv run python -m norgesgruppen.experiment train --name detect_v8l_1280 --model-size l --epochs 80 --imgsz 1280 --batch -1 --patience 20
# uv run python -m norgesgruppen.experiment train --name detect_v8x_1280 --model-size x --epochs 60 --imgsz 1280 --batch -1 --patience 20
```

* Nano, small and medium gave detection mAP of 0.9204, 0.9168 and 0.9120, respectively.
* Conclusion: No gain for larger models with this setup.

## Phase 2: Test hyperparameter tuning for nano model

* Try higher resolution, stronger augmentation and lower LR

```bash
uv run python -m norgesgruppen.experiment train --name detect_v8m_1600 --model-size n --epochs 80 --imgsz 1600 --batch -1 --patience 20
uv run python -m norgesgruppen.experiment train --name detect_v8m_1280_aug --model-size n --epochs 100 --imgsz 1280 --batch -1 --patience 20 --mosaic 1.0 --mixup 0.2
uv run python -m norgesgruppen.experiment train --name detect_v8m_1280_lowlr --model-size n --epochs 100 --imgsz 1280 --batch -1 --patience 25 --lr0 0.0005
```

## Phase 3: Train with multiple classes

```bash
uv run python -m norgesgruppen.experiment train --name classify_v8m_1280 --model-size n --epochs 120 --imgsz 1280 --batch -1 --patience 30 --multi-class
uv run python -m norgesgruppen.experiment train --name classify_v8m_1280_scratch --model-size n --epochs 120 --imgsz 1280 --batch -1 --patience 30 --multi-class --lr0 0.001
```

* Improveds scores to around 0.81

## Phase 3: Run on all data

```python
  uv run python -m norgesgruppen.experiment train \
    --name classify_v8n_1280_fulltrain \
    --model-size n \
    --epochs 120 \
    --imgsz 1280 \
    --batch -1 \
    --multi-class \
    --lr0 0.001 \
    --mosaic 0.5 \
    --mixup 0.1 \
    --optimizer AdamW \
    --patience 30 \
    --val-fraction 0 \
```

## Commands used to run experiments

Add a new submission from the experiments directory:

```bash
uv run python -m norgesgruppen.package --experiment-dir norgesgruppen/experiments/20260320_140101_classify_v8m_1280
```

## Run inside a Docker container

```bash
docker run --rm -v "$PWD/norgesgruppen/submissions:/app/submissions" -v "$PWD/output:/output" -v "$PWD/norgesgruppen/data/images:/data/images" \
  ng-submission-test /app/submissions/20260320_174636/submission/run.py --input /data/images --output /output/predictions.json
```
