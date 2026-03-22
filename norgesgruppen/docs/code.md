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
```

* Improves final score to around 0.81
* Updated sweep gives scores of around 0.90 -> test score: 0.87

### Finetuned once with 120 epochs, finetuned again for another 200 epochs

```bash
uv run python -m norgesgruppen.experiment train \
    --name classify_v8m_1280 \
    --model-size n \
    --epochs 200 \
    --imgsz 1280 \
    --batch -1 \
    --patience 30 \
    --multi-class \
    --pretrained-weights norgesgruppen/experiments/20260321_081516_classify_v8m_1280/train/weights/best.pt
```

* Updated sweep, final score is now 0.96 -> test_score: 0.89
* Another finetuning, final score is 0.97 -> test_score: 0.89
* Another finetuning, final score 0.9711 -> test_score: 0.8879 (worse)

```bash
uv run python -m norgesgruppen.experiment train \
    --name classify_v8m_1280_lr0005 \
    --model-size n \
    --epochs 200 \
    --imgsz 1280 \
    --batch -1 \
    --patience 30 \
    --multi-class \
    --lr0 0.0005 \
    --pretrained-weights norgesgruppen/experiments/20260321_103609_classify_v8m_1280/train/weights/best.pt
```

## Commands used to run experiments

Add a new submission from the experiments directory:

```bash
uv run python -m norgesgruppen.package --experiment-dir norgesgruppen/experiments/20260321_081516_classify_v8m_1280
```

## Run inside a Docker container

```bash
docker run --rm -v "$PWD/norgesgruppen/submissions:/app/submissions" -v "$PWD/output:/output" -v "$PWD/norgesgruppen/data/images:/data/images" \
  ng-submission-test /app/submissions/20260321_085827/submission/run.py --input /data/images --output /output/predictions.json
```

## Cross-validation sweeps

```bash
uv run python -m norgesgruppen.cross_validation \
    --name cv_classify_v8m \
    --mode classify \
    --folds 5 \
    --model-size m \
    --epochs 300 \
    --imgsz 1280 \
    --batch -1 \
    --patience 40 \
    --pretrained-detect norgesgruppen/experiments/20260321_081516_classify_v8m_1280/train/weights/best.pt
```

Each fold keeps its own dataset, weights, predictions, and threshold sweep under `norgesgruppen/experiments/cross_validation/<timestamp>_cv_classify_v8m/`. The command above reuses pretrained detection weights for faster convergence but you can also run from scratch (omit `--pretrained-detect`).
