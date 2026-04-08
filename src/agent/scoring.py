"""Score helpers shared across the OpenEnv evaluators."""

from __future__ import annotations


def clamp_score(raw_score: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """Clamp a score into the 0.0-1.0 range used by the environment."""

    return max(minimum, min(maximum, round(raw_score, 2)))


def ratio(numerator: float, denominator: float) -> float:
    """Safely divide two floats."""

    if denominator <= 0:
        return 0.0
    return numerator / denominator


def weighted_score(*parts: tuple[float, float]) -> float:
    """Combine weighted score components into a single normalized number."""

    total_weight = sum(weight for _, weight in parts)
    if total_weight <= 0:
        return 0.0
    return sum(value * weight for value, weight in parts) / total_weight
