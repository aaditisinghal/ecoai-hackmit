"""Emissions estimation for LLM inference.

The chain is:

    tokens -> FLOPs -> joules -> kWh -> grams CO2-equivalent

Each step and its coefficient:

1. **FLOPs per token.** A transformer forward pass costs roughly ``2 * N``
   floating point operations per token, where ``N`` is the number of *active*
   parameters (Kaplan et al., 2020, "Scaling Laws for Neural Language Models",
   Appendix B). For mixture-of-experts models the active count is far lower
   than the total, which is why the registry below tracks active parameters.

2. **Joules per FLOP.** Set from the accelerator's sustained throughput per
   watt. The default assumes an H100 SXM drawing ~700W and sustaining
   ~400 TFLOP/s in bf16, giving ~1.75e-12 J/FLOP. Override
   ``CARBON_JOULES_PER_FLOP`` if you know your own hardware.

3. **PUE.** Datacenter overhead - cooling, power distribution, networking -
   multiplies chip energy. Large operators report 1.1 to 1.2.

4. **Grid intensity.** Grams CO2-equivalent per kWh for the region the
   inference ran in.

This is a formula, not a measurement - it is not what CodeCarbon
(github.com/mlco2/codecarbon) or Zeus (Chung, Liu, Xie & Chowdhury, "Zeus:
Understanding and Optimizing GPU Energy Consumption of DNN Training", NSDI
2023, University of Michigan / ml-energy; github.com/ml-energy/zeus) do -
both read real power draw off the machine running inference via RAPL/NVML.
Neither is integrated here, and for the primary use case (optimizing a
prompt before it goes to a hosted third-party API) neither can be: nobody
but the provider has NVML access to the chip that will run the request.

A real-hardware check (an NVIDIA L4, Qwen2.5-1.5B-Instruct via vLLM, Zeus's
ZeusMonitor for actual NVML power sampling) found that shortening a prompt's
*input* barely moves a request's *measured* energy, because autoregressive
decoding of the (typically capped) output dominates total energy far more
than prefill length does. The formula's relative comparisons - bigger model
or dirtier grid costing more for the same token count - hold by construction
of the arithmetic and were not contradicted. Its implication that shortening
a prompt measurably cuts that request's real energy was not confirmed for
output-heavy requests. See the README's carbon section for the full writeup.

The region table is a static snapshot. For live data, wire in ElectricityMaps
or WattTime and pass the result as ``grid_intensity``.
"""

from __future__ import annotations

from dataclasses import dataclass

JOULES_PER_KWH = 3.6e6

# Active parameter counts. Open-weight models are exact; closed models are
# published estimates and community analysis, and should be treated as rough.
# Override per deployment by editing this table or passing active_params.
MODEL_ACTIVE_PARAMS: dict[str, float] = {
    # Open weights - exact
    "llama-3.1-8b": 8.0e9,
    "llama-3.1-70b": 70.0e9,
    "llama-3.3-70b": 70.0e9,
    "mistral-7b": 7.3e9,
    "mixtral-8x7b": 12.9e9,  # MoE: 2 of 8 experts active per token
    "qwen2.5-7b": 7.6e9,
    "qwen2.5-72b": 72.7e9,
    "gemma-2-9b": 9.2e9,
    "phi-3-mini": 3.8e9,
    # Closed weights - estimates only
    "gpt-4o": 200.0e9,
    "gpt-4o-mini": 8.0e9,
    "gpt-4": 280.0e9,
    "gpt-4-turbo": 200.0e9,
    "gpt-3.5-turbo": 20.0e9,
    "claude-3-opus": 300.0e9,
    "claude-3-sonnet": 70.0e9,
    "claude-3-haiku": 20.0e9,
    "claude-3-5-sonnet": 200.0e9,
    "gemini-1.5-pro": 200.0e9,
    "gemini-1.5-flash": 30.0e9,
}

# Grams CO2-equivalent per kWh, by cloud region. Static annual averages -
# real intensity swings by a factor of three across a single day.
REGION_GRID_INTENSITY: dict[str, float] = {
    # Very low carbon
    "eu-north-1": 45.0,      # Stockholm - hydro and nuclear
    "europe-north1": 45.0,
    "norway-east": 30.0,
    "ca-central-1": 130.0,   # Quebec - hydro
    "france-central": 85.0,  # nuclear
    "eu-west-3": 85.0,
    "brazil-south": 100.0,   # hydro
    # Moderate
    "us-west-2": 145.0,      # Oregon - hydro
    "us-west1": 145.0,
    "eu-west-1": 290.0,      # Ireland
    "uk-south": 250.0,
    "eu-central-1": 350.0,   # Frankfurt
    "us-east-1": 370.0,      # N. Virginia
    "us-east1": 370.0,
    "us-central1": 420.0,
    "us-east-2": 430.0,
    # High carbon
    "ap-southeast-2": 620.0,  # Sydney
    "ap-south-1": 700.0,      # Mumbai
    "ap-northeast-1": 480.0,  # Tokyo
    "ap-southeast-1": 500.0,  # Singapore
    "southafricanorth": 900.0,
}


@dataclass(frozen=True)
class CarbonCoefficients:
    """Resolved coefficients for one estimate."""

    joules_per_flop: float
    pue: float
    grid_intensity: float
    active_params: float

    @property
    def joules_per_token(self) -> float:
        return 2.0 * self.active_params * self.joules_per_flop * self.pue


@dataclass(frozen=True)
class CarbonEstimate:
    """Energy and emissions for a token count."""

    tokens: int
    kwh: float
    co2_g: float
    coefficients: CarbonCoefficients

    def to_dict(self) -> dict:
        return {"tokens": self.tokens, "kwh": self.kwh, "co2_g": self.co2_g}


@dataclass(frozen=True)
class CarbonSavings:
    """Difference between a before and after estimate."""

    before: CarbonEstimate
    after: CarbonEstimate

    @property
    def kwh_saved(self) -> float:
        return self.before.kwh - self.after.kwh

    @property
    def co2_g_saved(self) -> float:
        return self.before.co2_g - self.after.co2_g

    @property
    def tokens_saved(self) -> int:
        return self.before.tokens - self.after.tokens

    def to_dict(self) -> dict:
        return {
            "tokens_saved": self.tokens_saved,
            "kwh_saved": self.kwh_saved,
            "co2_g_saved": self.co2_g_saved,
            "kwh_before": self.before.kwh,
            "kwh_after": self.after.kwh,
            "co2_g_before": self.before.co2_g,
            "co2_g_after": self.after.co2_g,
        }


def normalize_model(model: str | None) -> str | None:
    """Map a vendor model id onto a registry key.

    Strips dated suffixes (``gpt-4o-mini-2024-07-18``) and provider prefixes
    (``anthropic.claude-3-haiku-v1``) so real-world identifiers resolve.
    """
    if not model:
        return None
    key = model.strip().lower()
    if "." in key:
        key = key.rsplit(".", 1)[-1]
    if key in MODEL_ACTIVE_PARAMS:
        return key
    # Longest registry key that prefixes the identifier wins, so
    # "claude-3-5-sonnet-20241022" prefers "claude-3-5-sonnet".
    matches = [name for name in MODEL_ACTIVE_PARAMS if key.startswith(name)]
    return max(matches, key=len) if matches else None


def resolve_active_params(model: str | None, default: float) -> float:
    known = normalize_model(model)
    return MODEL_ACTIVE_PARAMS[known] if known else default


def resolve_grid_intensity(region: str | None, default: float) -> float:
    if not region:
        return default
    return REGION_GRID_INTENSITY.get(region.strip().lower(), default)


class CarbonCalculator:
    """Turns token counts into energy and emissions figures.

    Built from :class:`ecoai.config.CarbonConfig` so every coefficient stays
    overridable through the environment.
    """

    def __init__(
        self,
        *,
        joules_per_flop: float,
        pue: float,
        default_grid_intensity: float,
        default_active_params: float,
    ) -> None:
        self.joules_per_flop = joules_per_flop
        self.pue = pue
        self.default_grid_intensity = default_grid_intensity
        self.default_active_params = default_active_params

    @classmethod
    def from_config(cls, config) -> CarbonCalculator:
        return cls(
            joules_per_flop=config.joules_per_flop,
            pue=config.pue,
            default_grid_intensity=config.default_grid_intensity,
            default_active_params=config.default_active_params,
        )

    def coefficients(
        self,
        *,
        model: str | None = None,
        region: str | None = None,
        active_params: float | None = None,
        grid_intensity: float | None = None,
    ) -> CarbonCoefficients:
        return CarbonCoefficients(
            joules_per_flop=self.joules_per_flop,
            pue=self.pue,
            grid_intensity=(
                grid_intensity
                if grid_intensity is not None
                else resolve_grid_intensity(region, self.default_grid_intensity)
            ),
            active_params=(
                active_params
                if active_params is not None
                else resolve_active_params(model, self.default_active_params)
            ),
        )

    def estimate(
        self,
        tokens: int,
        *,
        model: str | None = None,
        region: str | None = None,
        active_params: float | None = None,
        grid_intensity: float | None = None,
    ) -> CarbonEstimate:
        if tokens < 0:
            raise ValueError(f"tokens must be non-negative, got {tokens}")

        coeffs = self.coefficients(
            model=model,
            region=region,
            active_params=active_params,
            grid_intensity=grid_intensity,
        )
        joules = tokens * coeffs.joules_per_token
        kwh = joules / JOULES_PER_KWH
        return CarbonEstimate(
            tokens=tokens, kwh=kwh, co2_g=kwh * coeffs.grid_intensity, coefficients=coeffs
        )

    def savings(
        self,
        tokens_before: int,
        tokens_after: int,
        *,
        model: str | None = None,
        region: str | None = None,
        **kwargs,
    ) -> CarbonSavings:
        return CarbonSavings(
            before=self.estimate(tokens_before, model=model, region=region, **kwargs),
            after=self.estimate(tokens_after, model=model, region=region, **kwargs),
        )

    def greenest_regions(self, limit: int = 5) -> list[tuple[str, float]]:
        """Lowest-carbon regions in the static table, for routing suggestions."""
        return sorted(REGION_GRID_INTENSITY.items(), key=lambda item: item[1])[:limit]
