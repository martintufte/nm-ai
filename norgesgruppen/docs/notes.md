# Commands used to run experiments

## Initial sweep of experiments

```bash
uv run python -m norgesgruppen.experiment train --name detect_v8n_1280 --model-size n --epochs 100 --imgsz 1280 --batch -1 --patience 20
uv run python -m norgesgruppen.experiment train --name detect_v8s_1280 --model-size s --epochs 100 --imgsz 1280 --batch -1 --patience 20
uv run python -m norgesgruppen.experiment train --name detect_v8m_1280 --model-size m --epochs 100 --imgsz 1280 --batch -1 --patience 20
uv run python -m norgesgruppen.experiment train --name detect_v8l_1280 --model-size l --epochs 80 --imgsz 1280 --batch -1 --patience 20
uv run python -m norgesgruppen.experiment train --name detect_v8x_1280 --model-size x --epochs 60 --imgsz 1280 --batch -1 --patience 20
```
