#!/usr/bin/env bash
# Run experiments on GPU machine. Execute from the nm-ai repo root.
# Usage: bash norgesgruppen/run_experiments.sh [experiment_number]
#   No args  = run all in order (skips 0)
#   "0"      = eval-only on a weights file
#   "3"      = run only experiment 3
#   "3 5 7"  = run experiments 3, 5, and 7
set -euo pipefail

run() {
    local num="$1"; shift
    local label="$1"; shift
    echo ""
    echo "=========================================="
    echo "  EXPERIMENT $num: $label"
    echo "=========================================="
    uv run python -m norgesgruppen.experiment "$@"
}

experiments=(
# ── 0: Eval-only (inference + threshold sweep, no training) ──────────
# Edit --weights to point to your .pt file
"0|eval_only|eval --weights norgesgruppen/weights/detect_v8m_1280.pt --imgsz 1280"

# ── PHASE 1: Detection-only (single-class) ──────────────────────────
# Maximizes the 70% detection mAP component.
# Model size sweep at 1280px (native shelf image resolution matters for small products).

# 1) YOLOv8-N baseline (fast, ~3M params)
"1|detect_v8n_1280|train --name detect_v8n_1280 --model-size n --epochs 100 --imgsz 1280 --batch -1 --patience 20"

# 2) YOLOv8-S (11M params, good speed/accuracy tradeoff)
"2|detect_v8s_1280|train --name detect_v8s_1280 --model-size s --epochs 100 --imgsz 1280 --batch -1 --patience 20"

# 3) YOLOv8-M (25M params, strong baseline)
"3|detect_v8m_1280|train --name detect_v8m_1280 --model-size m --epochs 100 --imgsz 1280 --batch -1 --patience 20"

# 4) YOLOv8-L (43M params, more capacity)
"4|detect_v8l_1280|train --name detect_v8l_1280 --model-size l --epochs 80 --imgsz 1280 --batch -1 --patience 20"

# 5) YOLOv8-X (68M params, maximum capacity, check if L4 24GB fits)
"5|detect_v8x_1280|train --name detect_v8x_1280 --model-size x --epochs 60 --imgsz 1280 --batch -1 --patience 20"

# ── PHASE 2: Augmentation & hyperparameter tuning ───────────────────
# Run these after Phase 1 to see which model size wins, then tune the best one.

# 6) Best-size with higher resolution (if L4 memory allows)
"6|detect_v8m_1600|train --name detect_v8m_1600 --model-size m --epochs 80 --imgsz 1600 --batch -1 --patience 20"

# 7) Best-size with stronger augmentation (heavy mosaic + copy-paste for dense scenes)
"7|detect_v8m_1280_aug|train --name detect_v8m_1280_aug --model-size m --epochs 100 --imgsz 1280 --batch -1 --patience 20 --mosaic 1.0 --mixup 0.2"

# 8) Best-size with lower LR (sometimes helps with small datasets)
"8|detect_v8m_1280_lowlr|train --name detect_v8m_1280_lowlr --model-size m --epochs 100 --imgsz 1280 --batch -1 --patience 25 --lr0 0.0005"

# 9) YOLOv8-M with SGD instead of AdamW
"9|detect_v8m_1280_sgd|train --name detect_v8m_1280_sgd --model-size m --epochs 100 --imgsz 1280 --batch -1 --patience 20 --optimizer SGD --lr0 0.01"

# ── PHASE 3: Multi-class (detection + classification) ───────────────
# Uses the 356 product categories for the 30% classification mAP.
# Set --pretrained-weights to best detection model from Phase 1/2.

# 10) Multi-class from best detection weights (fill in path after Phase 1)
"10|classify_v8m_1280|train --name classify_v8m_1280 --model-size m --epochs 120 --imgsz 1280 --batch -1 --patience 30 --multi-class --lr0 0.0005"

# 11) Multi-class from scratch (compare vs fine-tuning from detection)
"11|classify_v8m_1280_scratch|train --name classify_v8m_1280_scratch --model-size m --epochs 120 --imgsz 1280 --batch -1 --patience 30 --multi-class --lr0 0.001"
)

# Parse which experiments to run
if [ $# -eq 0 ]; then
    selected=""  # run all
else
    selected="$*"
fi

for entry in "${experiments[@]}"; do
    IFS='|' read -r num label args <<< "$entry"
    num=$(echo "$num" | tr -d ' ')

    # Skip experiment 0 unless explicitly requested
    if [ -z "$selected" ] && [ "$num" = "0" ]; then continue; fi

    if [ -n "$selected" ]; then
        skip=true
        for s in $selected; do
            if [ "$s" = "$num" ]; then skip=false; break; fi
        done
        if $skip; then continue; fi
    fi

    eval "run $num $label $args"
done

echo ""
echo "=========================================="
echo "  ALL DONE — check leaderboard:"
echo "  cat norgesgruppen/experiments/leaderboard.txt"
echo "=========================================="
