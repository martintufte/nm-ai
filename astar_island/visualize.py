"""Visualization for Astar Island terrain maps.

Generates:
1. Full board visualization with terrain colors matching app.ainm.no
2. 2x3 grid of individual terrain masks (water, plains, mountain, settlement, forest, coastal)

Colors are matched to the official competition visualization.

Usage:
    python -m astar_island.visualize --round 1 --seed 0
"""

import argparse
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from numpy.typing import NDArray

from astar_island.fetch_data import load_round
from astar_island.model import find_coastal_cells

LOGGER = logging.getLogger(__name__)

PLOTS_DIR = Path(__file__).parent / "plots"

# Colors matched to the official app.ainm.no visualization
TERRAIN_COLORS = {
    "water": "#145a96",  # Darker blue (ocean)
    "plains": "#d4b96a",  # Tan/sand
    "settlement": "#f08c00",  # Vibrant orange
    "port": "#30b5c7",  # Cyan
    "ruin": "#8b1a1a",  # Dark red/maroon
    "forest": "#2d7a2d",  # Dark green
    "mountain": "#7a7f8a",  # Slate gray
}

# Full board colormap: class indices 0-5 map to [empty, settlement, port, ruin, forest, mountain]
# But raw grid has: 10=water, 11=plains, 1=settlement, 2=port, 4=forest, 5=mountain
BOARD_RAW_COLORS = {
    10: TERRAIN_COLORS["water"],
    11: TERRAIN_COLORS["plains"],
    1: TERRAIN_COLORS["settlement"],
    2: TERRAIN_COLORS["port"],
    4: TERRAIN_COLORS["forest"],
    5: TERRAIN_COLORS["mountain"],
}


# Prediction channels: (class_index, name, color hex)
# Ordered: row 1 = Plains/Ocean/Empty, Forest, Mountain; row 2 = Settlement, Port, Ruin
CHANNELS = [
    (0, "Plains/Ocean/Empty", TERRAIN_COLORS["plains"]),
    (4, "Forest", TERRAIN_COLORS["forest"]),
    (5, "Mountain", TERRAIN_COLORS["mountain"]),
    (1, "Settlement", TERRAIN_COLORS["settlement"]),
    (3, "Ruin", TERRAIN_COLORS["ruin"]),
    (2, "Port", TERRAIN_COLORS["port"]),
]


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    return (
        int(hex_color[1:3], 16) / 255,
        int(hex_color[3:5], 16) / 255,
        int(hex_color[5:7], 16) / 255,
    )


def _make_cmap(hex_color: str) -> LinearSegmentedColormap:
    """Create a colormap from black → terrain color."""
    rgb = _hex_to_rgb(hex_color)
    return LinearSegmentedColormap.from_list("", [(0.12, 0.12, 0.12), rgb])


def plot_full_board(
    raw_grid: NDArray[np.int16],
    title: str = "A* Island",
    ax: plt.Axes | None = None,
) -> plt.Axes:
    """Plot the full board with terrain colors."""
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 8))

    # Build RGB image from raw grid values
    h, w = raw_grid.shape
    rgb = np.zeros((h, w, 3), dtype=np.float64)
    for raw_val, hex_color in BOARD_RAW_COLORS.items():
        mask = raw_grid == raw_val
        rgb[mask] = _hex_to_rgb(hex_color)

    ax.imshow(rgb, interpolation="nearest")
    ax.set_title(title, fontsize=14, fontweight="bold")
    ax.set_xticks([])
    ax.set_yticks([])
    return ax


def plot_mask(
    mask: NDArray[np.bool_],
    color: str,
    title: str,
    ax: plt.Axes,
) -> None:
    """Plot a single terrain mask with the given color on a dark background."""
    h, w = mask.shape
    rgb = np.full((h, w, 3), 0.12)  # Dark background
    rgb[mask] = _hex_to_rgb(color)

    ax.imshow(rgb, interpolation="nearest")
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xticks([])
    ax.set_yticks([])


def plot_mask_grid(
    raw_grid: NDArray[np.int16],
    water_mask: NDArray[np.bool_],
    plains_mask: NDArray[np.bool_],
    mountain_mask: NDArray[np.bool_],
    settlement_mask: NDArray[np.bool_],
    forest_mask: NDArray[np.bool_],
    coastal_mask: NDArray[np.bool_],
    suptitle: str = "Terrain Masks",
) -> plt.Figure:
    """Plot a 2x3 grid of terrain masks."""
    fig, axes = plt.subplots(2, 3, figsize=(14, 10), facecolor="#1e1e1e")
    fig.suptitle(suptitle, fontsize=16, fontweight="bold", color="white")

    masks_and_colors = [
        (plains_mask, TERRAIN_COLORS["plains"], "Plains"),
        (forest_mask, TERRAIN_COLORS["forest"], "Forest"),
        (mountain_mask, TERRAIN_COLORS["mountain"], "Mountain"),
        (settlement_mask, TERRAIN_COLORS["settlement"], "Settlement"),
        (water_mask, TERRAIN_COLORS["water"], "Water"),
        (coastal_mask, TERRAIN_COLORS["port"], "Coastal"),
    ]

    for ax, (mask, color, title) in zip(axes.flat, masks_and_colors, strict=False):
        plot_mask(mask, color, title, ax)
        ax.set_title(title, fontsize=12, fontweight="bold", color="white")

    fig.tight_layout(rect=[0, 0, 1, 0.95])  # ty: ignore[invalid-argument-type]
    return fig


def plot_heatmap_grid(
    probs: NDArray[np.float64],
    suptitle: str = "Probability Channels",
) -> plt.Figure:
    """Plot a 2x3 grid of per-class probability heatmaps."""
    fig, axes = plt.subplots(2, 3, figsize=(14, 10), facecolor="#1e1e1e")
    fig.suptitle(suptitle, fontsize=16, fontweight="bold", color="white")

    for ax, (ch, name, hex_color) in zip(axes.flat, CHANNELS, strict=False):
        cmap = _make_cmap(hex_color)
        im = ax.imshow(probs[:, :, ch], cmap=cmap, vmin=0, vmax=1, interpolation="nearest")
        ax.set_title(name, fontsize=12, fontweight="bold", color="white")
        ax.set_xticks([])
        ax.set_yticks([])
        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(colors="white", labelsize=8)

    fig.tight_layout(rect=[0, 0, 1, 0.95])  # ty: ignore[invalid-argument-type]
    return fig


def plot_heatmap_combined(
    probs: NDArray[np.float64],
    title: str = "Combined Probability Map",
) -> plt.Figure:
    """Plot a combined map where each cell's color is the weighted blend of all 6 channels."""
    h, w, _ = probs.shape
    rgb = np.zeros((h, w, 3), dtype=np.float64)

    for ch, _, hex_color in CHANNELS:
        color = np.array(_hex_to_rgb(hex_color))
        rgb += probs[:, :, ch, np.newaxis] * color[np.newaxis, np.newaxis, :]

    # Clip to valid range (weighted sum of valid colors can exceed 1 in bright areas)
    rgb = np.clip(rgb, 0, 1)

    fig, ax = plt.subplots(figsize=(8, 8), facecolor="#1e1e1e")
    ax.imshow(rgb, interpolation="nearest")
    ax.set_title(title, fontsize=14, fontweight="bold", color="white")
    ax.set_xticks([])
    ax.set_yticks([])
    fig.tight_layout()
    return fig


def visualize_round(round_number: int, seed_index: int) -> None:
    """Generate and save visualizations for a specific round and seed."""
    data = load_round(round_number)
    raw_grid = data["raw_grids"][seed_index]
    water_mask = data["water_masks"][seed_index]
    plains_mask = data["plains_masks"][seed_index]
    mountain_mask = data["mountain_masks"][seed_index]
    settlement_mask = data["settlement_masks"][seed_index] | data["port_masks"][seed_index]
    forest_mask = data["forest_masks"][seed_index]
    coastal_mask = find_coastal_cells(water_mask)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    prefix = f"round_{round_number:02d}_seed_{seed_index}"

    # Full board
    fig, ax = plt.subplots(figsize=(8, 8), facecolor="#1e1e1e")
    plot_full_board(raw_grid, title=f"Round {round_number} — Seed {seed_index}", ax=ax)
    ax.set_title(ax.get_title(), color="white")
    fig.tight_layout()
    board_path = PLOTS_DIR / f"{prefix}_board.png"
    fig.savefig(board_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    # Mask grid
    fig = plot_mask_grid(
        raw_grid=raw_grid,
        water_mask=water_mask,
        plains_mask=plains_mask,
        mountain_mask=mountain_mask,
        settlement_mask=settlement_mask,
        forest_mask=forest_mask,
        coastal_mask=coastal_mask,
        suptitle=f"Round {round_number} — Seed {seed_index} — Terrain Masks",
    )
    masks_path = PLOTS_DIR / f"{prefix}_masks.png"
    fig.savefig(masks_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    LOGGER.info("Saved: %s", board_path)
    LOGGER.info("Saved: %s", masks_path)

    # Ground truth heatmaps (if available)
    if "ground_truth" in data and not np.isnan(data["ground_truth"]).all():
        gt = data["ground_truth"][seed_index]

        fig = plot_heatmap_grid(
            gt,
            suptitle=f"Round {round_number} — Seed {seed_index} — Ground Truth Channels",
        )
        gt_channels_path = PLOTS_DIR / f"{prefix}_gt_channels.png"
        fig.savefig(gt_channels_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        LOGGER.info("Saved: %s", gt_channels_path)

        fig = plot_heatmap_combined(
            gt,
            title=f"Round {round_number} — Seed {seed_index} — Ground Truth Combined",
        )
        gt_combined_path = PLOTS_DIR / f"{prefix}_gt_combined.png"
        fig.savefig(gt_combined_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
        LOGGER.info("Saved: %s", gt_combined_path)
    else:
        LOGGER.warning("No ground truth available for round %d", round_number)


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize Astar Island terrain maps")
    parser.add_argument("--round", type=int, default=1, help="Round number (default: 1)")
    parser.add_argument("--seed", type=int, default=0, help="Seed index 0-4 (default: 0)")
    args = parser.parse_args()

    visualize_round(args.round, args.seed)


if __name__ == "__main__":
    main()
