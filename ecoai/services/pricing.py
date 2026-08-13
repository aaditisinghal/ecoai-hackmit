"""Model pricing, used to convert saved tokens into saved dollars.

A static snapshot in USD per one million tokens. Vendor prices change often;
this table needs a periodic review and is not a billing source of truth.

The previous implementation hardcoded per-1K prices inline in the dashboard
handler and assumed a fixed 70/30 input/output split without saying so.
The split is still an assumption - receipts record a single total token count,
not a breakdown - but it now lives in one named constant that callers can
override.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Assumed share of tokens that are input rather than output. Prompt
#: optimization only ever shrinks the input side, so this is what the cost
#: saving is scaled by.
DEFAULT_INPUT_SHARE = 0.7


@dataclass(frozen=True)
class ModelPrice:
    """USD per 1,000,000 tokens."""

    input_per_mtok: float
    output_per_mtok: float


MODEL_PRICING: dict[str, ModelPrice] = {
    "gpt-4o": ModelPrice(2.50, 10.00),
    "gpt-4o-mini": ModelPrice(0.15, 0.60),
    "gpt-4-turbo": ModelPrice(10.00, 30.00),
    "gpt-4": ModelPrice(30.00, 60.00),
    "gpt-3.5-turbo": ModelPrice(0.50, 1.50),
    "claude-3-opus": ModelPrice(15.00, 75.00),
    "claude-3-5-sonnet": ModelPrice(3.00, 15.00),
    "claude-3-sonnet": ModelPrice(3.00, 15.00),
    "claude-3-haiku": ModelPrice(0.25, 1.25),
    "claude-3": ModelPrice(3.00, 15.00),
    "gemini-1.5-pro": ModelPrice(1.25, 5.00),
    "gemini-1.5-flash": ModelPrice(0.075, 0.30),
    "gemini-pro": ModelPrice(0.50, 1.50),
    "llama-3.1-8b": ModelPrice(0.05, 0.08),
    "llama-3.1-70b": ModelPrice(0.35, 0.40),
    "mistral-7b": ModelPrice(0.05, 0.10),
    "mixtral-8x7b": ModelPrice(0.24, 0.24),
}

#: Applied when a receipt names a model that is not in the table.
FALLBACK_PRICE = ModelPrice(0.15, 0.60)


def resolve_price(model: str | None) -> ModelPrice:
    """Look up pricing, tolerating dated and prefixed model identifiers."""
    if not model:
        return FALLBACK_PRICE

    key = model.strip().lower()
    if "." in key:
        key = key.rsplit(".", 1)[-1]
    if key in MODEL_PRICING:
        return MODEL_PRICING[key]

    matches = [name for name in MODEL_PRICING if key.startswith(name)]
    return MODEL_PRICING[max(matches, key=len)] if matches else FALLBACK_PRICE


def cost_saved_usd(
    tokens_saved: int, model: str | None, *, input_share: float = DEFAULT_INPUT_SHARE
) -> float:
    """Dollar value of the tokens an optimization avoided sending."""
    if tokens_saved <= 0:
        return 0.0
    price = resolve_price(model)
    input_tokens = tokens_saved * input_share
    output_tokens = tokens_saved * (1.0 - input_share)
    return (
        input_tokens * price.input_per_mtok + output_tokens * price.output_per_mtok
    ) / 1_000_000
