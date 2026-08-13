"""Carbon estimation and pricing."""

from __future__ import annotations

import pytest

from ecoai.config import CarbonConfig
from ecoai.services.carbon import (
    JOULES_PER_KWH,
    CarbonCalculator,
    normalize_model,
    resolve_grid_intensity,
)
from ecoai.services.pricing import cost_saved_usd, resolve_price


@pytest.fixture
def calculator() -> CarbonCalculator:
    return CarbonCalculator.from_config(CarbonConfig.from_env())


class TestModelResolution:
    def test_exact_match(self):
        assert normalize_model("gpt-4o-mini") == "gpt-4o-mini"

    def test_dated_suffix_is_stripped(self):
        assert normalize_model("gpt-4o-mini-2024-07-18") == "gpt-4o-mini"

    def test_provider_prefix_is_stripped(self):
        assert normalize_model("anthropic.claude-3-haiku") == "claude-3-haiku"

    def test_longest_prefix_wins(self):
        """"claude-3-5-sonnet-x" must not resolve to the shorter "claude-3"."""
        assert normalize_model("claude-3-5-sonnet-20241022") == "claude-3-5-sonnet"

    def test_unknown_model_returns_none(self):
        assert normalize_model("some-model-nobody-has-heard-of") is None

    def test_none_and_empty(self):
        assert normalize_model(None) is None
        assert normalize_model("") is None


class TestGridIntensity:
    def test_known_region(self):
        assert resolve_grid_intensity("eu-north-1", 480.0) == 45.0

    def test_case_insensitive(self):
        assert resolve_grid_intensity("EU-NORTH-1", 480.0) == 45.0

    def test_unknown_region_falls_back(self):
        assert resolve_grid_intensity("mars-central-1", 480.0) == 480.0

    def test_missing_region_falls_back(self):
        assert resolve_grid_intensity(None, 480.0) == 480.0


class TestEstimation:
    def test_zero_tokens_is_zero_emissions(self, calculator):
        estimate = calculator.estimate(0, model="gpt-4o-mini")
        assert estimate.kwh == 0.0
        assert estimate.co2_g == 0.0

    def test_negative_tokens_is_rejected(self, calculator):
        with pytest.raises(ValueError, match="non-negative"):
            calculator.estimate(-1)

    def test_emissions_scale_linearly_with_tokens(self, calculator):
        one = calculator.estimate(1000, model="gpt-4o-mini").co2_g
        two = calculator.estimate(2000, model="gpt-4o-mini").co2_g
        assert two == pytest.approx(one * 2)

    def test_bigger_model_costs_more(self, calculator):
        small = calculator.estimate(1000, model="gpt-4o-mini").co2_g
        large = calculator.estimate(1000, model="gpt-4").co2_g
        assert large > small

    def test_greener_region_emits_less_for_identical_work(self, calculator):
        dirty = calculator.estimate(1000, model="gpt-4o-mini", region="ap-south-1")
        clean = calculator.estimate(1000, model="gpt-4o-mini", region="eu-north-1")
        assert clean.co2_g < dirty.co2_g
        # Same energy, different grid.
        assert clean.kwh == pytest.approx(dirty.kwh)

    def test_chain_matches_the_documented_formula(self, calculator):
        """tokens x 2N x J/FLOP x PUE / 3.6e6 x gCO2/kWh."""
        tokens = 1000
        estimate = calculator.estimate(
            tokens, active_params=1e9, grid_intensity=400.0
        )
        expected_joules = tokens * 2 * 1e9 * calculator.joules_per_flop * calculator.pue
        assert estimate.kwh == pytest.approx(expected_joules / JOULES_PER_KWH)
        assert estimate.co2_g == pytest.approx(estimate.kwh * 400.0)

    def test_explicit_overrides_beat_the_registry(self, calculator):
        estimate = calculator.estimate(
            1000, model="gpt-4", region="eu-north-1", active_params=1e9, grid_intensity=1000.0
        )
        assert estimate.coefficients.active_params == 1e9
        assert estimate.coefficients.grid_intensity == 1000.0


class TestSavings:
    def test_savings_are_the_difference(self, calculator):
        savings = calculator.savings(1000, 600, model="gpt-4o-mini")
        assert savings.tokens_saved == 400
        assert savings.co2_g_saved == pytest.approx(savings.before.co2_g - savings.after.co2_g)
        assert savings.co2_g_saved > 0

    def test_no_reduction_means_no_savings(self, calculator):
        savings = calculator.savings(500, 500, model="gpt-4o-mini")
        assert savings.tokens_saved == 0
        assert savings.co2_g_saved == pytest.approx(0.0)

    def test_dict_shape(self, calculator):
        payload = calculator.savings(100, 50).to_dict()
        assert set(payload) == {
            "tokens_saved",
            "kwh_saved",
            "co2_g_saved",
            "kwh_before",
            "kwh_after",
            "co2_g_before",
            "co2_g_after",
        }

    def test_greenest_regions_are_sorted_ascending(self, calculator):
        regions = calculator.greenest_regions(5)
        intensities = [intensity for _, intensity in regions]
        assert intensities == sorted(intensities)
        assert len(regions) == 5


class TestPricing:
    def test_known_model(self):
        assert resolve_price("gpt-4o").input_per_mtok == 2.50

    def test_dated_model_resolves(self):
        assert resolve_price("gpt-4o-2024-11-20").input_per_mtok == 2.50

    def test_unknown_model_uses_fallback(self):
        assert resolve_price("nonexistent-model").input_per_mtok == 0.15

    def test_no_savings_is_zero_cost(self):
        assert cost_saved_usd(0, "gpt-4o") == 0.0
        assert cost_saved_usd(-100, "gpt-4o") == 0.0

    def test_expensive_model_saves_more_per_token(self):
        assert cost_saved_usd(1000, "gpt-4") > cost_saved_usd(1000, "gpt-4o-mini")

    def test_cost_scales_linearly(self):
        assert cost_saved_usd(2000, "gpt-4o") == pytest.approx(cost_saved_usd(1000, "gpt-4o") * 2)
