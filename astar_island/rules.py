"""Game rules validation for Astar Island.

Tracks boolean assumptions about the simulation mechanics and validates them
against observed viewport data from queries. Rules start as True (assumed to hold)
and are set to False if a counterexample is observed.

Usage:
    rules = GameRules()
    # After each viewport query, validate against initial + observed state:
    rules.validate(initial_grid, viewport_grid, viewport_x, viewport_y)
    rules.summary()
"""

import logging
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from astar_island.client import MAP_SIZE

LOGGER = logging.getLogger(__name__)


def _adjacent_4(mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
    """Return mask of cells 4-adjacent to any True cell."""
    result = np.zeros_like(mask)
    for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        result |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return result


@dataclass
class GameRules:
    """Boolean rules about the Astar Island simulation.

    Each rule starts as True (assumed). When validate() finds a counterexample,
    the rule is set to False and a log message is emitted.
    """

    # Static terrain rules
    static_mountains: bool = True          # Mountains never change class
    static_water: bool = True              # Water/ocean never changes class

    # Port rules
    ports_adjacent_to_water: bool = True   # Ports are always 4-adjacent to water
    ports_were_settlements: bool = True    # Ports only appear where initial terrain was settlement or plains

    # Settlement rules
    no_settlements_on_water: bool = True   # Settlements never appear on initial water cells
    no_settlements_on_mountains: bool = True  # Settlements never appear on initial mountain cells

    # Ruin rules
    no_ruins_on_water: bool = True         # Ruins never appear on water
    no_ruins_on_mountains: bool = True     # Ruins never appear on mountains

    # Forest rules
    no_forests_on_water: bool = True       # Forests never appear on water
    no_forests_on_mountains: bool = True   # Forests never appear on mountains

    # General constraints
    water_stays_empty_class: bool = True   # Initial water cells remain class 0 (empty/ocean)
    mountains_stay_mountain: bool = True   # Initial mountain cells remain class 5

    _violations: dict[str, list[str]] = field(default_factory=dict, repr=False)

    def validate(
        self,
        initial_grid: NDArray[np.int16],
        viewport_grid: list[list[int]],
        viewport_x: int,
        viewport_y: int,
    ) -> None:
        """Validate rules against a viewport observation.

        Args:
            initial_grid: Full (40, 40) initial raw grid for this seed.
            viewport_grid: Observed 15x15 viewport grid (raw API values).
            viewport_x: Top-left x of viewport.
            viewport_y: Top-left y of viewport.
        """
        vp = np.array(viewport_grid, dtype=np.int16)
        vh, vw = vp.shape

        # Extract the corresponding region from the initial grid
        init_region = initial_grid[viewport_y:viewport_y + vh, viewport_x:viewport_x + vw]

        # Water mask for the full map (needed for adjacency checks)
        full_water = initial_grid == 10
        water_adj = _adjacent_4(full_water)

        # Viewport-local masks from initial state
        init_water = init_region == 10
        init_mountain = init_region == 5

        # Viewport-local masks from observed (final) state
        obs_water = vp == 10
        obs_mountain = vp == 5
        obs_settlement = vp == 1
        obs_port = vp == 2
        obs_ruin_raw = vp == 3  # raw value for ruin in final state
        obs_forest = vp == 4

        # For ruins: we need to figure out the raw value used in viewport responses.
        # The initial grid uses: 1=settlement, 2=port, 4=forest, 5=mountain, 10=water, 11=plains
        # The final state may use different values. Check for any unknown values.
        known_values = {1, 2, 4, 5, 10, 11}
        obs_unique = set(np.unique(vp).tolist())
        unknown_values = obs_unique - known_values
        # Ruins might appear as value 3 in the final state
        obs_ruin = np.zeros_like(vp, dtype=bool)
        for val in unknown_values:
            obs_ruin |= (vp == val)
        # Also check explicit value 3
        obs_ruin |= obs_ruin_raw

        # Water adjacency in the viewport region
        vp_water_adj = water_adj[viewport_y:viewport_y + vh, viewport_x:viewport_x + vw]

        loc = f"viewport ({viewport_x}, {viewport_y})"

        # --- Validate each rule ---

        if self.static_mountains and np.any(init_mountain & ~obs_mountain):
            self._violate("static_mountains", f"Mountain changed at {loc}")

        if self.static_water and np.any(init_water & ~obs_water):
            self._violate("static_water", f"Water changed at {loc}")

        if self.ports_adjacent_to_water and np.any(obs_port & ~vp_water_adj):
            self._violate("ports_adjacent_to_water", f"Port not adjacent to water at {loc}")

        if self.ports_were_settlements:
            init_could_have_port = (init_region == 1) | (init_region == 2) | (init_region == 11)
            if np.any(obs_port & ~init_could_have_port):
                self._violate("ports_were_settlements",
                              f"Port on unexpected initial terrain at {loc}")

        if self.no_settlements_on_water and np.any(obs_settlement & init_water):
            self._violate("no_settlements_on_water", f"Settlement on initial water at {loc}")

        if self.no_settlements_on_mountains and np.any(obs_settlement & init_mountain):
            self._violate("no_settlements_on_mountains", f"Settlement on initial mountain at {loc}")

        if self.no_ruins_on_water and np.any(obs_ruin & init_water):
            self._violate("no_ruins_on_water", f"Ruin on initial water at {loc}")

        if self.no_ruins_on_mountains and np.any(obs_ruin & init_mountain):
            self._violate("no_ruins_on_mountains", f"Ruin on initial mountain at {loc}")

        if self.no_forests_on_water and np.any(obs_forest & init_water):
            self._violate("no_forests_on_water", f"Forest on initial water at {loc}")

        if self.no_forests_on_mountains and np.any(obs_forest & init_mountain):
            self._violate("no_forests_on_mountains", f"Forest on initial mountain at {loc}")

        if self.water_stays_empty_class:
            # Water cells should remain as water (value 10) in final state
            if np.any(init_water & ~obs_water):
                self._violate("water_stays_empty_class",
                              f"Initial water cell changed in final state at {loc}")

        if self.mountains_stay_mountain:
            if np.any(init_mountain & ~obs_mountain):
                self._violate("mountains_stay_mountain",
                              f"Initial mountain cell changed in final state at {loc}")

    def validate_ground_truth(
        self,
        initial_grid: NDArray[np.int16],
        ground_truth: NDArray[np.float64],
    ) -> None:
        """Validate rules against ground truth probability distributions.

        Checks whether the ground truth assigns non-trivial probability to
        states that would violate the rules.

        Args:
            initial_grid: Full (40, 40) initial raw grid.
            ground_truth: (40, 40, 6) probability array.
        """
        init_water = initial_grid == 10
        init_mountain = initial_grid == 5
        full_water_adj = _adjacent_4(init_water)

        # Threshold: if ground truth assigns > 1% to a class, it can happen
        threshold = 0.01

        # Classes: 0=empty, 1=settlement, 2=port, 3=ruin, 4=forest, 5=mountain
        gt_settlement = ground_truth[:, :, 1] > threshold
        gt_port = ground_truth[:, :, 2] > threshold
        gt_ruin = ground_truth[:, :, 3] > threshold
        gt_forest = ground_truth[:, :, 4] > threshold
        gt_mountain = ground_truth[:, :, 5] > threshold
        gt_empty = ground_truth[:, :, 0] > (1.0 - threshold)  # almost certain empty

        if self.static_mountains and np.any(init_mountain & ~gt_mountain):
            self._violate("static_mountains", "GT: mountain cell not predicted as mountain")

        if self.static_water and np.any(init_water & ~gt_empty):
            self._violate("static_water", "GT: water cell not predicted as staying empty")

        if self.ports_adjacent_to_water and np.any(gt_port & ~full_water_adj):
            self._violate("ports_adjacent_to_water", "GT: port probability where not adjacent to water")

        if self.no_settlements_on_water and np.any(gt_settlement & init_water):
            self._violate("no_settlements_on_water", "GT: settlement probability on water")

        if self.no_settlements_on_mountains and np.any(gt_settlement & init_mountain):
            self._violate("no_settlements_on_mountains", "GT: settlement probability on mountain")

        if self.no_ruins_on_water and np.any(gt_ruin & init_water):
            self._violate("no_ruins_on_water", "GT: ruin probability on water")

        if self.no_ruins_on_mountains and np.any(gt_ruin & init_mountain):
            self._violate("no_ruins_on_mountains", "GT: ruin probability on mountain")

        if self.no_forests_on_water and np.any(gt_forest & init_water):
            self._violate("no_forests_on_water", "GT: forest probability on water")

        if self.no_forests_on_mountains and np.any(gt_forest & init_mountain):
            self._violate("no_forests_on_mountains", "GT: forest probability on mountain")

    def _violate(self, rule_name: str, detail: str) -> None:
        """Mark a rule as violated."""
        setattr(self, rule_name, False)
        if rule_name not in self._violations:
            self._violations[rule_name] = []
        self._violations[rule_name].append(detail)
        LOGGER.warning("Rule violated: %s — %s", rule_name, detail)

    def summary(self) -> str:
        """Return a summary of all rules and their status."""
        rules = [
            "static_mountains", "static_water",
            "ports_adjacent_to_water", "ports_were_settlements",
            "no_settlements_on_water", "no_settlements_on_mountains",
            "no_ruins_on_water", "no_ruins_on_mountains",
            "no_forests_on_water", "no_forests_on_mountains",
            "water_stays_empty_class", "mountains_stay_mountain",
        ]
        lines = ["Game Rules Status:"]
        for name in rules:
            status = getattr(self, name)
            mark = "HOLDS" if status else "BROKEN"
            line = f"  {mark:6s}  {name}"
            if name in self._violations:
                line += f"  ({len(self._violations[name])} violations)"
            lines.append(line)
        return "\n".join(lines)
