"""Unit tests for the Astar Island prediction pipeline."""

import numpy as np
import pytest

from astar_island.client import MAP_SIZE
from astar_island.client import NUM_CLASSES
from astar_island.predict import DEFAULT_KERNELS
from astar_island.predict import PRIOR_EMPTY_LAND
from astar_island.predict import PRIOR_FOREST
from astar_island.predict import PRIOR_MOUNTAIN
from astar_island.predict import PRIOR_SETTLEMENT
from astar_island.predict import PRIOR_WATER
from astar_island.predict import SeedState
from astar_island.predict import SymmetricKernel
from astar_island.predict import apply_diffusion_step
from astar_island.predict import build_prior
from astar_island.predict import convolve2d
from astar_island.predict import create_seed_state
from astar_island.predict import enforce_symmetry
from astar_island.predict import ensure_min_probability
from astar_island.predict import find_coastal_cells
from astar_island.predict import parse_raw_grid
from astar_island.predict import predict_seed


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
    return create_seed_state(0, simple_map)


class TestSymmetricKernel:
    def test_symmetry_structure(self) -> None:
        k = SymmetricKernel(center=0.4, edge=0.1, corner=0.05)
        arr = k.to_array()

        # Check up/down symmetry
        np.testing.assert_array_almost_equal(arr[0, :], arr[2, :])
        # Check left/right symmetry
        np.testing.assert_array_almost_equal(arr[:, 0], arr[:, 2])
        # Check all edges are equal
        assert arr[0, 1] == arr[1, 0] == arr[2, 1] == arr[1, 2]

    def test_sums_to_one(self) -> None:
        k = SymmetricKernel(center=0.4, edge=0.1, corner=0.05)
        arr = k.to_array()
        np.testing.assert_almost_equal(arr.sum(), 1.0)

    def test_normalization(self) -> None:
        # Even with arbitrary values, to_array normalizes to sum 1
        k = SymmetricKernel(center=10.0, edge=2.0, corner=1.0)
        arr = k.to_array()
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
        state = create_seed_state(0, simple_map)
        assert state.water_mask.shape == (MAP_SIZE, MAP_SIZE)
        assert state.mountain_mask.shape == (MAP_SIZE, MAP_SIZE)
        assert state.settlement_mask.shape == (MAP_SIZE, MAP_SIZE)
        assert state.forest_mask.shape == (MAP_SIZE, MAP_SIZE)
        assert state.coastal_mask.shape == (MAP_SIZE, MAP_SIZE)

    def test_mountain_mask(self, simple_map: list[list[int]]) -> None:
        state = create_seed_state(0, simple_map)
        assert state.mountain_mask[20, 20]
        assert state.mountain_mask[19, 19]
        assert not state.mountain_mask[0, 0]

    def test_settlement_mask(self, simple_map: list[list[int]]) -> None:
        state = create_seed_state(0, simple_map)
        assert state.settlement_mask[10, 10]
        assert state.settlement_mask[29, 29]
        assert not state.settlement_mask[0, 0]

    def test_water_mask(self, simple_map: list[list[int]]) -> None:
        state = create_seed_state(0, simple_map)
        # Boundary is water (value 10)
        assert state.water_mask[0, 0]
        assert state.water_mask[0, MAP_SIZE - 1]
        # Interior plains are not water
        assert not state.water_mask[15, 15]


class TestBuildPrior:
    def test_output_shape(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state)
        assert probs.shape == (MAP_SIZE, MAP_SIZE, NUM_CLASSES)

    def test_sums_to_one(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state)
        sums = probs.sum(axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)

    def test_water_cells_get_water_prior(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state)
        water_cell = np.where(simple_seed_state.water_mask)
        if len(water_cell[0]) > 0:
            y, x = water_cell[0][0], water_cell[1][0]
            np.testing.assert_array_almost_equal(probs[y, x], PRIOR_WATER)

    def test_mountain_cells_get_mountain_prior(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state)
        np.testing.assert_array_almost_equal(probs[20, 20], PRIOR_MOUNTAIN)

    def test_settlement_cells_get_settlement_prior(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state)
        # Settlement at (10, 10) - check it got a settlement prior (not empty land)
        assert probs[10, 10, 1] > PRIOR_EMPTY_LAND[1]  # higher settlement prob

    def test_forest_cells_get_forest_prior(self, simple_seed_state: SeedState) -> None:
        probs = build_prior(simple_seed_state)
        # Forest ring at row 2
        np.testing.assert_array_almost_equal(probs[2, 5], PRIOR_FOREST)


class TestConvolve2d:
    def test_identity_kernel(self) -> None:
        arr = np.random.default_rng(42).random((10, 10))
        kernel = np.array([[0, 0, 0], [0, 1, 0], [0, 0, 0]])
        result = convolve2d(arr, kernel)
        np.testing.assert_array_almost_equal(result, arr)

    def test_uniform_kernel_smooths(self) -> None:
        arr = np.zeros((10, 10))
        arr[5, 5] = 1.0
        kernel = np.ones((3, 3)) / 9.0
        result = convolve2d(arr, kernel)

        # Center should decrease, neighbors should increase
        assert result[5, 5] < 1.0
        assert result[4, 5] > 0.0
        assert result[5, 4] > 0.0

    def test_preserves_shape(self) -> None:
        arr = np.random.default_rng(42).random((MAP_SIZE, MAP_SIZE))
        kernel = np.ones((3, 3)) / 9.0
        result = convolve2d(arr, kernel)
        assert result.shape == arr.shape


class TestApplyDiffusionStep:
    def test_output_shape(self, simple_seed_state: SeedState) -> None:

        static_mask = simple_seed_state.water_mask | simple_seed_state.mountain_mask
        result = apply_diffusion_step(
            simple_seed_state.probs,
            DEFAULT_KERNELS,
            static_mask,
            simple_seed_state.probs.copy(),
        )
        assert result.shape == (MAP_SIZE, MAP_SIZE, NUM_CLASSES)

    def test_sums_to_one(self, simple_seed_state: SeedState) -> None:

        static_mask = simple_seed_state.water_mask | simple_seed_state.mountain_mask
        result = apply_diffusion_step(
            simple_seed_state.probs,
            DEFAULT_KERNELS,
            static_mask,
            simple_seed_state.probs.copy(),
        )
        sums = result.sum(axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)

    def test_static_cells_preserved(self, simple_seed_state: SeedState) -> None:

        static_mask = simple_seed_state.water_mask | simple_seed_state.mountain_mask
        static_probs = simple_seed_state.probs.copy()
        result = apply_diffusion_step(
            simple_seed_state.probs,
            DEFAULT_KERNELS,
            static_mask,
            static_probs,
        )
        np.testing.assert_array_almost_equal(result[static_mask], static_probs[static_mask])


class TestEnforceSymmetry:
    def test_result_is_symmetric(self) -> None:
        rng = np.random.default_rng(42)
        probs = rng.random((MAP_SIZE, MAP_SIZE, NUM_CLASSES))
        probs /= probs.sum(axis=-1, keepdims=True)

        sym = enforce_symmetry(probs)

        # Up/down symmetric
        np.testing.assert_array_almost_equal(sym, np.flip(sym, axis=0))
        # Left/right symmetric
        np.testing.assert_array_almost_equal(sym, np.flip(sym, axis=1))

    def test_preserves_already_symmetric(self) -> None:
        probs = np.ones((MAP_SIZE, MAP_SIZE, NUM_CLASSES)) / NUM_CLASSES
        sym = enforce_symmetry(probs)
        np.testing.assert_array_almost_equal(sym, probs)


class TestEnsureMinProbability:
    def test_no_zeros(self) -> None:
        probs = np.zeros((MAP_SIZE, MAP_SIZE, NUM_CLASSES))
        probs[:, :, 0] = 1.0  # all probability on class 0
        result = ensure_min_probability(probs)
        assert (result >= 0.01).all()

    def test_sums_to_one(self) -> None:
        rng = np.random.default_rng(42)
        probs = rng.random((MAP_SIZE, MAP_SIZE, NUM_CLASSES))
        probs /= probs.sum(axis=-1, keepdims=True)
        result = ensure_min_probability(probs)
        sums = result.sum(axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)


class TestPredictSeed:
    def test_output_shape(self, simple_seed_state: SeedState) -> None:
        result = predict_seed(simple_seed_state, num_steps=1)
        assert result.shape == (MAP_SIZE, MAP_SIZE, NUM_CLASSES)

    def test_sums_to_one(self, simple_seed_state: SeedState) -> None:
        result = predict_seed(simple_seed_state, num_steps=1)
        sums = result.sum(axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)

    def test_no_zeros(self, simple_seed_state: SeedState) -> None:
        result = predict_seed(simple_seed_state, num_steps=1)
        assert (result >= 0.01).all()

    def test_symmetric_output(self, simple_seed_state: SeedState) -> None:
        result = predict_seed(simple_seed_state, num_steps=1)
        np.testing.assert_array_almost_equal(result, np.flip(result, axis=0))
        np.testing.assert_array_almost_equal(result, np.flip(result, axis=1))

    def test_zero_steps_still_valid(self, simple_seed_state: SeedState) -> None:
        result = predict_seed(simple_seed_state, num_steps=0)
        assert result.shape == (MAP_SIZE, MAP_SIZE, NUM_CLASSES)
        assert (result >= 0.01).all()
        sums = result.sum(axis=-1)
        np.testing.assert_array_almost_equal(sums, 1.0)


class TestPriorDistributions:
    """Verify all prior distributions sum to 1."""

    @pytest.mark.parametrize(
        "prior",
        [PRIOR_WATER, PRIOR_MOUNTAIN, PRIOR_SETTLEMENT, PRIOR_FOREST, PRIOR_EMPTY_LAND],
    )
    def test_sums_to_one(self, prior: np.ndarray) -> None:
        np.testing.assert_almost_equal(prior.sum(), 1.0)

    @pytest.mark.parametrize(
        "prior",
        [PRIOR_WATER, PRIOR_MOUNTAIN, PRIOR_SETTLEMENT, PRIOR_FOREST, PRIOR_EMPTY_LAND],
    )
    def test_no_zeros(self, prior: np.ndarray) -> None:
        assert (prior > 0).all()

    @pytest.mark.parametrize(
        "prior",
        [PRIOR_WATER, PRIOR_MOUNTAIN, PRIOR_SETTLEMENT, PRIOR_FOREST, PRIOR_EMPTY_LAND],
    )
    def test_has_six_classes(self, prior: np.ndarray) -> None:
        assert prior.shape == (NUM_CLASSES,)
