# Code for running experiments

Example run experiment on round 1 using the perfect predictor

```bash
uv run python -m astar_island.experiment --round 1 --predictor diffusion --queries 50
```

## Benchmark runs
```bash
uv run python -m astar_island.benchmark
uv run python -m astar_island.benchmark --rounds 1-16 --queries 50
```
