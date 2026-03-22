"""Visualization for Astar Island terrain maps.

Generates:
1. Full board visualization with terrain colors matching app.ainm.no
2. 2x3 grid of individual terrain masks (water, plains, mountain, settlement, forest, coastal)

Colors are matched to the official competition visualization.
"""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from numpy.typing import NDArray

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


def plot_query_coverage(
    raw_grids: list[NDArray[np.int16]],
    query_counts: list[NDArray[np.int32]],
    suptitle: str = "Query Coverage",
) -> plt.Figure:
    """Plot a 2xN grid: top row = initial board, bottom row = query heatmap overlay.

    Args:
        raw_grids: Per-seed initial grids.
        query_counts: Per-seed (H, W) query count arrays.
        suptitle: Figure title.
    """
    n_seeds = len(raw_grids)
    fig, axes = plt.subplots(2, n_seeds, figsize=(4 * n_seeds, 8), facecolor="#1e1e1e")

    max_count = max(int(c.max()) for c in query_counts)
    max_count = max(max_count, 1)

    for seed_idx in range(n_seeds):
        grid = raw_grids[seed_idx]
        counts = query_counts[seed_idx]

        # Top row: initial board
        ax_board = axes[0, seed_idx]
        h, w = grid.shape
        rgb = np.zeros((h, w, 3), dtype=np.float64)
        for raw_val, hex_color in BOARD_RAW_COLORS.items():
            mask = grid == raw_val
            rgb[mask] = _hex_to_rgb(hex_color)
        ax_board.imshow(rgb, interpolation="nearest")
        ax_board.set_title(f"Seed {seed_idx}", fontsize=12, fontweight="bold", color="white")
        ax_board.set_xticks([])
        ax_board.set_yticks([])

        # Bottom row: board with query heatmap overlay
        ax_heat = axes[1, seed_idx]
        ax_heat.imshow(rgb, interpolation="nearest")

        # Green overlay with alpha proportional to query count
        overlay = np.zeros((h, w, 4), dtype=np.float64)
        green = _hex_to_rgb("#44cc44")
        norm_counts = counts.astype(np.float64) / max_count
        overlay[:, :, 0] = green[0]
        overlay[:, :, 1] = green[1]
        overlay[:, :, 2] = green[2]
        overlay[:, :, 3] = norm_counts * 0.95

        ax_heat.imshow(overlay, interpolation="nearest")

        # Label: observed cells + avg queries on non-static cells
        static = (grid == 10) | (grid == 5)
        dynamic_counts = counts[~static]
        avg_dynamic = float(dynamic_counts.mean()) if dynamic_counts.size > 0 else 0.0
        n_observed = int((counts > 0).sum())
        ax_heat.set_title(
            f"{n_observed}/{h * w} observed, avg {avg_dynamic:.1f}x on dynamic",
            fontsize=10,
            color="white",
        )
        ax_heat.set_xticks([])
        ax_heat.set_yticks([])

    fig.suptitle(suptitle, fontsize=16, fontweight="bold", color="white")
    fig.tight_layout(rect=[0, 0, 1, 0.95])  # ty: ignore[invalid-argument-type]
    return fig
