.PHONY: norgesgruppen

NORGESGRUPPEN_IMAGES ?= norgesgruppen/data/NM_NGD_coco_dataset/train/images
NORGESGRUPPEN_OUTPUT ?= /tmp/ng_output.json
NORGESGRUPPEN_ANNOTATIONS ?= norgesgruppen/data/NM_NGD_coco_dataset/train/annotations.json

ngd:
	uv run python -m norgesgruppen.baseline --annotations $(NORGESGRUPPEN_ANNOTATIONS) --output $(NORGESGRUPPEN_OUTPUT)
