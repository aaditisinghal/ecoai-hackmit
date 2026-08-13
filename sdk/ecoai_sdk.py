#!/usr/bin/env python3
"""EcoAI SDK — a client for the EcoAI Portal API.

Single file, one dependency (``requests``). Drop it next to your code, or
install it however you package internal modules.

    pip install requests

    from ecoai_sdk import EcoAI

    eco = EcoAI(api_key="ecoai_...")          # or set ECOAI_API_KEY
    result = eco.optimize("Could you please summarize this?")
    print(result.optimized, result.tokens_saved, result.co2_g_saved)

Optimization happens server-side. That is deliberate: the portal and the SDK
then always agree on what a given prompt produced, and improvements to the
optimizer reach every client without anyone upgrading a package. The previous
SDK reimplemented a different, simpler algorithm locally and reported a
hardcoded quality score, so its numbers never matched the dashboard's.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import requests

__version__ = "2.0.0"

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 30


class EcoAIError(RuntimeError):
    """Base class for every SDK error."""


class AuthenticationError(EcoAIError):
    """The API key was missing, malformed, or rejected."""


class RateLimitError(EcoAIError):
    """The account exceeded its rate limit."""


class ValidationError(EcoAIError):
    """The server rejected the request as invalid."""


@dataclass
class OptimizationResult:
    """What the portal returned for one prompt."""

    original: str
    optimized: str
    strategy: str
    tokens_before: int
    tokens_after: int
    tokens_saved: int
    reduction_ratio: float
    retention_score: float
    co2_g_saved: float
    kwh_saved: float
    transformations: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    receipt_id: str | None = None

    @classmethod
    def from_response(cls, payload: dict[str, Any]) -> OptimizationResult:
        carbon = payload.get("carbon") or {}
        return cls(
            original=payload.get("original", ""),
            optimized=payload.get("optimized", ""),
            strategy=payload.get("strategy", "balanced"),
            tokens_before=payload.get("tokens_before", 0),
            tokens_after=payload.get("tokens_after", 0),
            tokens_saved=payload.get("tokens_saved", 0),
            reduction_ratio=payload.get("reduction_ratio", 0.0),
            retention_score=payload.get("retention_score", 0.0),
            co2_g_saved=carbon.get("co2_g_saved", 0.0),
            kwh_saved=carbon.get("kwh_saved", 0.0),
            transformations=payload.get("transformations", []),
            warnings=payload.get("warnings", []),
            receipt_id=payload.get("receipt_id"),
        )

    def __str__(self) -> str:
        return self.optimized


class EcoAI:
    """Client for the EcoAI Portal.

    Args:
        api_key: Your key. Falls back to ``ECOAI_API_KEY``.
        base_url: Portal origin. Falls back to ``ECOAI_BASE_URL``.
        timeout: Per-request timeout in seconds.
        session: An existing ``requests.Session`` to reuse.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("ECOAI_API_KEY", "")
        if not self.api_key:
            raise AuthenticationError(
                "No API key. Pass api_key= or set the ECOAI_API_KEY environment variable."
            )

        self.base_url = (base_url or os.environ.get("ECOAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": f"ecoai-sdk/{__version__}",
            }
        )

    # -- Public API --------------------------------------------------------

    def optimize(
        self,
        prompt: str,
        *,
        strategy: str = "balanced",
        model: str | None = None,
        region: str | None = None,
        persist: bool = True,
    ) -> OptimizationResult:
        """Optimize a prompt.

        Args:
            prompt: The prompt to shorten.
            strategy: ``conservative``, ``balanced`` or ``aggressive``.
            model: Model id, used to pick energy and pricing coefficients.
            region: Cloud region, used to pick grid carbon intensity.
            persist: Record a receipt. Set False for a dry run.
        """
        payload = self._request(
            "POST",
            "/api/v1/optimize",
            json={
                "prompt": prompt,
                "strategy": strategy,
                "model": model,
                "region": region,
                "persist": persist,
            },
        )
        return OptimizationResult.from_response(payload)

    def send_receipts(self, receipts: list[dict[str, Any]]) -> dict[str, Any]:
        """Report optimizations performed outside the portal.

        Each receipt needs at least ``receipt_id``, ``tokens_before`` and
        ``tokens_after``. Ingestion is idempotent on ``receipt_id``, so
        retrying a timed-out call never double-counts.

        Returns the ingest report, including anything rejected and why.
        """
        events = [
            {
                "type": "receipt",
                "receipt_id": receipt["receipt_id"],
                "payload": receipt,
            }
            for receipt in receipts
        ]
        return self._request("POST", "/api/v1/receipts/batch", json={"events": events})

    def receipts(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """List your receipts, newest first."""
        payload = self._request(
            "GET", "/api/v1/receipts", params={"limit": limit, "offset": offset}
        )
        return payload.get("receipts", [])

    def summary(self) -> dict[str, Any]:
        """All-time totals for your account."""
        return self._request("GET", "/api/v1/metrics/summary")

    def timeseries(self, days: int = 30) -> list[dict[str, Any]]:
        """Daily savings for the last ``days`` days."""
        payload = self._request("GET", "/api/v1/metrics/timeseries", params={"days": days})
        return payload.get("series", [])

    def me(self) -> dict[str, Any]:
        """Your account details."""
        return self._request("GET", "/api/v1/me")

    def regions(self) -> list[dict[str, Any]]:
        """Grid carbon intensity by region, lowest first.

        Useful for carbon-aware routing: send batch work to the greenest
        region you can reach.
        """
        payload = self._request("GET", "/api/v1/carbon/regions")
        return payload.get("regions", [])

    # -- Transport ---------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.base_url}{path}"

        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
        except requests.RequestException as exc:
            raise EcoAIError(f"Could not reach {url}: {exc}") from exc

        if response.status_code == 401:
            raise AuthenticationError("API key rejected. Generate a new one from your profile.")
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "a moment")
            raise RateLimitError(f"Rate limit exceeded. Retry after {retry_after}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise EcoAIError(
                f"{url} returned {response.status_code} with a non-JSON body."
            ) from exc

        if response.status_code == 400:
            raise ValidationError(payload.get("message", "The server rejected that request."))
        if not response.ok:
            raise EcoAIError(
                payload.get("message", f"Request failed with status {response.status_code}.")
            )

        return payload


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: ECOAI_API_KEY=... python ecoai_sdk.py 'your prompt here'")
        raise SystemExit(1)

    client = EcoAI()
    outcome = client.optimize(" ".join(sys.argv[1:]))

    print("Optimized:", outcome.optimized)
    print(f"Tokens:    {outcome.tokens_before} -> {outcome.tokens_after} "
          f"({outcome.reduction_ratio:.1%} saved)")
    print(f"CO2e:      {outcome.co2_g_saved:.6f} g avoided")
    print(f"Retention: {outcome.retention_score:.2f}")
    for warning in outcome.warnings:
        print("Warning:  ", warning)
