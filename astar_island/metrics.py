"""Scoring metrics for Astar Island predictions.

Implements the entropy-weighted KL divergence score used by the competition.

Formula:
    KL(p||q) = sum(p * log(p / q)) per cell
    entropy(p) = -sum(p * log(p)) per cell
    weighted_kl = sum(entropy * kl) / sum(entropy) over all cells
    score = clamp(100 * exp(-3 * weighted_kl), 0, 100)
"""

import numpy as np
from numpy.typing import NDArray


def entropy_weighted_kl_score(
    ground_truth: NDArray[np.float64],
    predictions: NDArray[np.float64],
    eps: float = 1e-12,
) -> float:
    """Compute the entropy-weighted KL divergence score used in competition scoring.

    Args:
        ground_truth: (40, 40, 6) true probability distributions.
        predictions: (40, 40, 6) predicted probability distributions.
        eps: Small constant to avoid log(0).

    Returns:
        Score in [0, 100]. 100 = perfect, 0 = terrible.
    """
    p = np.clip(ground_truth, eps, 1.0)
    q = np.clip(predictions, eps, 1.0)

    # Per-cell KL divergence: KL(p || q) = sum_i p_i * log(p_i / q_i)
    kl = np.sum(p * np.log(p / q), axis=-1)  # (40, 40)

    # Per-cell entropy: H(p) = -sum_i p_i * log(p_i)
    entropy = -np.sum(p * np.log(p), axis=-1)  # (40, 40)

    total_entropy = entropy.sum()
    if total_entropy < eps:
        return 100.0

    weighted_kl = np.sum(entropy * kl) / total_entropy
    score = 100.0 * np.exp(-3.0 * weighted_kl)
    return float(np.clip(score, 0.0, 100.0))
