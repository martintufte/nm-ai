"""Unit tests for the Astar Island prediction pipeline."""

import numpy as np
import pytest

from astar_island.client import N_CLASSES
from astar_island.model import IslandModel
from astar_island.model import SeedState
from astar_island.model import create_seed_state
from astar_island.model import find_coastal_cells
from astar_island.model import parse_raw_grid
from astar_island.predictor.diffuser import DiffusionParams
from astar_island.predictor.diffuser import DiffusionPredictor
from astar_island.predictor.diffuser import SymmetricKernel
from astar_island.predictor.diffuser import TerrainPriors
from astar_island.predictor.diffuser import apply_diffusion
from astar_island.predictor.diffuser import build_prior
from astar_island.predictor.diffuser import _convolve2d

# Default instances for test access
_PRIORS = TerrainPriors()
_DIFFUSION = DiffusionParams()
from astar_island.rules import _ensure_min_probability as ensure_min_probability

MAP_SIZE = 40  # Test grid size


def _make_simple_map() -> list[list[int]]:
    """Create a 40x40 map using raw API grid values (10=water, 11=plains, etc.)."""
    grid = [[10] * MAP_SIZE for _ in range(MAP_SIZE)]  # water border

    # Interior plains
    for y in range(2, MAP_SIZE - 2):
        for x in range(2, MAP_SIZE - 2):
            grid[y][x] = 11  # plains

    # Ring of forest at row/col 2 and 37
    for i in range(2, MAP_SIZE - 2):
        grid[2][i] = 4
        grid[MAP_SIZE - 3][i] = 4
        grid[i][2] = 4
        grid[i][MAP_SIZE - 3] = 4

    # Mountains in the center
    grid[20][20] = 5
    grid[19][20] = 5
    grid[20][19] = 5
    grid[19][19] = 5

    # Settlements (symmetrically placed)
    grid[10][10] = 1
    grid[10][29] = 1
    grid[29][10] = 1
    grid[29][29] = 1

    return grid


@pytest.fixture
def simple_map() -> list[list[int]]:
    return _make_simple_map()


@pytest.fixture
def simple_seed_state(simple_map: list[list[int]]) -> SeedState:
    grid = np.array(simple_map, dtype=np.int16)
    return create_seed_state(0, grid)


@pytest.fixture
def simple_probs(simple_seed_state: SeedState) -> np.ndarray:
    return build_prior(simple_seed_state, _PRIORS)


class TestSymmetricKernel:
    def test_symmetry_structure(self) -> None:
        k = SymmetricKernel(edge=0.1)
        arr = k.to_array()

        # Check up/down symmetry
        np.testing.assert_array_almost_equal(arr[0, :], arr[2, :])
        # Check left/right symmetry
        np.testing.assert_array_almost_equal(arr[:, 0], arr[:, 2])
        # Check all edges are equal
        assert arr[0, 1] == arr[1, 0] == arr[2, 1] == arr[1, 2]
        # Corners should be zero
        assert arr[0, 0] == arr[0, 2] == arr[2, 0] == arr[2, 2] == 0.0

    def test_sums_to_one(self) -> None:
        k = SymmetricKernel(edge=0.1)
        arr = k.to_array()
        np.testing.assert_almost_equal(arr.sum(), 1.0)

    def test_center_derived(self) -> None:
        k = SymmetricKernel(edge=0.1)
        arr = k.to_array()
        np.testing.assert_almost_equal(arr[1, 1], 0.6)  # 1 - 4*0.1

    def test_identity(self) -> None:
        k = SymmetricKernel(edge=0.0)
        arr = k.to_array()
        np.testing.assert_almost_equal(arr[1, 1], 1.0)
        np.testing.assert_almost_equal(arr.sum(), 1.0)


class TestParseRawGrid:
    def test_water_from_value_10(self) -> None:
        grid = np.full((MAP_SIZE, MAP_SIZE), 10, dtype=np.int16)
        masks = parse_raw_grid(grid)
        assert masks["water_mask"].all()

    def test_no_water_from_plains(self) -> None:
        grid = np.full((MAP_SIZE, MAP_SIZE), 11, dtype=np.int16)
        masks = parse_raw_grid(grid)
        assert not masks["water_mask"].any()

    def test_settlement_includes_ports(self) -> None:
        grid = np.full((MAP_SIZE, MAP_SIZE), 11, dtype=np.int16)
        grid[5, 5] = 1  # settlement
        grid[6, 6] = 2  # port
        masks = parse_raw_grid(grid)
        assert masks["settlement_mask"][5, 5]
        assert masks["settlement_mask"][6, 6]


class TestFindCoastalCells:
    def test_adjacent_to_water(self) -> None:
        water = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
        water[0, :] = True  # top row is water

        coastal = find_coastal_cells(water)

        # Row 1 should be coastal (adjacent to water row 0)
        assert coastal[1, 5]
        # Row 0 should NOT be coastal (it's water)
        assert not coastal[0, 5]
        # Row 2 should NOT be coastal (not adjacent to water)
        assert not coastal[2, 5]


class TestCreateSeedState:
    def test_mask_shapes(self, simple_map: list[list[int]]) -> None:
        grid = np.array(simple_map, dtype=np.int16)
        state = create_seed_state(0, grid)
        assert state.water_mask.shape == (MAP_SIZE, MAP_SIZE)
        assert state.mountain_mask.shape == (MAP_SIZE, MAP_SIZE)
        assert state.settlement_mask.shape == (MAP_SIZE, MAP_SIZE)
        assert state.forest_mask.shape == (MAP_SIZE, MAP_SIZE)
        assert state.coastal_mask.shape == (MAP_SIZE, MAP_SIZE)

    def test_mountain_mask(self, simple_map: list[list[int]]) -> None:
        grid = np.array(simple_map, dtype=np.int16)
        state = create_seed_state(0, grid)
        assert state.mountain_mask[20, 20]
        assert state.mountain_mask[19, 19]
        assert not state.mountain_mask[0, 0]

    def test_settlement_mask(self, simple_map: list[list[int]]) -> None:
        grid = np.array(simple_map, dtype=np.int16)
        state = create_seed_state(0, grid)
        assert state.settlement_mask[10, 10]
        assert state.settlement_mask[29, 29]
        assert not state.settlement_mask[0, 0]

    def test_water_mask(self, simple_map: list[list[int]]) -> None:
        grid = np.array(simple_map, dtype=np.int16)
        state = create_seed_state(0, grid)
        # Boundary is water (value 10)
        assert state.water_mask[0, 0]
        assert state.water_mask[0, MAP_SIZE - 1]
        # Interior plains are not water
        assert not state.water_mask[15, 15]


class TestBuildPrior:
    def test_output_shape(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state, _PRIORS)
        assert probs.shape == (MAP_SIZE, MAP_SIZE, N_CLASSES)

    def test_sums_to_one(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state, _PRIORS)
        sums = probs.sum(axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)

    def test_water_cells_get_water_prior(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state, _PRIORS)
        water_cell = np.where(simple_seed_state.water_mask)
        if len(water_cell[0]) > 0:
            y, x = water_cell[0][0], water_cell[1][0]
            np.testing.assert_array_almost_equal(probs[y, x], _PRIORS.water)

    def test_mountain_cells_get_mountain_prior(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state, _PRIORS)
        np.testing.assert_array_almost_equal(probs[20, 20], _PRIORS.mountain)

    def test_settlement_cells_get_settlement_prior(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state, _PRIORS)
        # Settlement at (10, 10) - check it got a settlement prior (not empty land)
        assert probs[10, 10, 1] > _PRIORS.empty_land[1]  # higher settlement prob

    def test_forest_cells_get_forest_prior(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state, _PRIORS)
        # Forest ring at row 2
        np.testing.assert_array_almost_equal(probs[2, 5], _PRIORS.forest)


class TestConvolve2d:
    def test_identity_kernel(self) -> None:
        arr = np.random.default_rng(42).random((10, 10))
        kernel = np.array([[0, 0, 0], [0, 1, 0], [0, 0, 0]])
        result = _convolve2d(arr, kernel)
        np.testing.assert_array_almost_equal(result, arr)

    def test_uniform_kernel_smooths(self) -> None:
        arr = np.zeros((10, 10))
        arr[5, 5] = 1.0
        kernel = np.ones((3, 3)) / 9.0
        result = _convolve2d(arr, kernel)

        # Center should decrease, neighbors should increase
        assert result[5, 5] < 1.0
        assert result[4, 5] > 0.0
        assert result[5, 4] > 0.0

    def test_preserves_shape(self) -> None:
        arr = np.random.default_rng(42).random((MAP_SIZE, MAP_SIZE))
        kernel = np.ones((3, 3)) / 9.0
        result = _convolve2d(arr, kernel)
        assert result.shape == arr.shape


class TestApplyDiffusion:
    def test_output_shape(
        self, simple_seed_state: SeedState, simple_probs: np.ndarray,
    ) -> None:
        static_mask = simple_seed_state.water_mask | simple_seed_state.mountain_mask
        result = apply_diffusion(
            simple_probs, DiffusionParams(n_steps=1), static_mask, simple_probs.copy(),
        )
        assert result.shape == (MAP_SIZE, MAP_SIZE, N_CLASSES)

    def test_sums_to_one(
        self, simple_seed_state: SeedState, simple_probs: np.ndarray,
    ) -> None:
        static_mask = simple_seed_state.water_mask | simple_seed_state.mountain_mask
        result = apply_diffusion(
            simple_probs, DiffusionParams(n_steps=1), static_mask, simple_probs.copy(),
        )
        sums = result.sum(axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)

    def test_static_cells_preserved(
        self, simple_seed_state: SeedState, simple_probs: np.ndarray,
    ) -> None:
        static_mask = simple_seed_state.water_mask | simple_seed_state.mountain_mask
        static_probs = simple_probs.copy()
        result = apply_diffusion(
            simple_probs, DiffusionParams(n_steps=1), static_mask, static_probs,
        )
        np.testing.assert_array_almost_equal(result[static_mask], static_probs[static_mask])


class TestEnsureMinProbability:
    def test_no_zeros(self) -> None:
        probs = np.zeros((MAP_SIZE, MAP_SIZE, N_CLASSES))
        probs[:, :, 0] = 1.0  # all probability on class 0
        result = ensure_min_probability(probs)
        assert (result >= 0.01).all()

    def test_sums_to_one(self) -> None:
        rng = np.random.default_rng(42)
        probs = rng.random((MAP_SIZE, MAP_SIZE, N_CLASSES))
        probs /= probs.sum(axis=-1, keepdims=True)
        result = ensure_min_probability(probs)
        sums = result.sum(axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)


class TestDiffusionPredictor:
    def _predict(self, simple_map: list[list[int]], num_steps: int = 1) -> np.ndarray:
        from astar_island.client import RoundData, SeedData  # noqa: PLC0415

        predictor = DiffusionPredictor(diffusion=DiffusionParams(n_steps=num_steps))
        grid = np.array(simple_map, dtype=np.int16)
        h, w = grid.shape
        round_data = RoundData(
            id="test", round_number=1, status="active",
            map_width=w, map_height=h, seeds_count=1,
            seeds=[SeedData(grid=grid, settlements=[])],
        )
        model = IslandModel.from_round_data(round_data, predictor)
        return model.predict(0)

    def test_output_shape(self, simple_map: list[list[int]]) -> None:
        result = self._predict(simple_map)
        assert result.shape == (MAP_SIZE, MAP_SIZE, N_CLASSES)

    def test_sums_to_one(self, simple_map: list[list[int]]) -> None:
        result = self._predict(simple_map)
        sums = result.sum(axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)

    def test_min_prob_on_feasible_classes(self, simple_map: list[list[int]]) -> None:
        result = self._predict(simple_map)
        grid = np.array(simple_map, dtype=np.int16)
        dynamic = (grid != 10) & (grid != 5)  # not water, not mountain
        # Non-zero probs should all be >= min_prob
        nonzero = result[dynamic] > 0
        assert (result[dynamic][nonzero] >= 0.01).all()

    def test_static_cells_deterministic(self, simple_map: list[list[int]]) -> None:
        result = self._predict(simple_map)
        grid = np.array(simple_map, dtype=np.int16)
        # Water cells: all prob on class 0
        water = grid == 10
        np.testing.assert_array_almost_equal(result[water, 0], 1.0)
        # Mountain cells: all prob on class 5
        mountain = grid == 5
        np.testing.assert_array_almost_equal(result[mountain, 5], 1.0)

    def test_zero_steps_still_valid(self, simple_map: list[list[int]]) -> None:
        result = self._predict(simple_map, num_steps=0)
        assert result.shape == (MAP_SIZE, MAP_SIZE, N_CLASSES)
        sums = result.sum(axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)


class TestPriorDistributions:
    """Verify all prior distributions sum to 1."""

    @pytest.mark.parametrize(
        "prior",
        [_PRIORS.water, _PRIORS.mountain, _PRIORS.settlement, _PRIORS.forest, _PRIORS.empty_land],
    )
    def test_sums_to_one(self, prior: np.ndarray) -> None:
        np.testing.assert_almost_equal(prior.sum(), 1.0)

    @pytest.mark.parametrize(
        "prior",
        [_PRIORS.settlement, _PRIORS.forest, _PRIORS.empty_land],
    )
    def test_dynamic_priors_zero_classes(self, prior: np.ndarray) -> None:
        assert prior[2] == 0.0  # port derived via p_port
        assert prior[3] == 0.0  # ruin derived via p_ruin
        assert prior[5] == 0.0  # mountain enforced by rules
        assert (prior[[0, 1, 4]] > 0).all()  # empty, settle, forest > 0

    def test_p_port_and_p_ruin_in_valid_range(self) -> None:
        assert 0.0 < _DIFFUSION.p_port < 1.0
        assert 0.0 < _DIFFUSION.p_ruin < 1.0

    @pytest.mark.parametrize(
        "prior",
        [_PRIORS.water, _PRIORS.mountain],
    )
    def test_static_priors_are_deterministic(self, prior: np.ndarray) -> None:
        assert prior.max() == 1.0
        assert (prior >= 0).all()

    @pytest.mark.parametrize(
        "prior",
        [_PRIORS.water, _PRIORS.mountain, _PRIORS.settlement, _PRIORS.forest, _PRIORS.empty_land],
    )
    def test_has_six_classes(self, prior: np.ndarray) -> None:
        assert prior.shape == (N_CLASSES,)
