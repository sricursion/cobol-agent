"""OpenEnv client for the COBOL modernization environment."""

from __future__ import annotations

from typing import Any

from openenv.core.client_types import StepResult
from openenv.core.env_client import EnvClient

from models import ModernizationAction, ModernizationObservation, ModernizationState


class CobolModernizationEnv(
    EnvClient[ModernizationAction, ModernizationObservation, ModernizationState]
):
    """Type-safe OpenEnv client for the COBOL modernization environment."""

    def _step_payload(self, action: ModernizationAction) -> dict[str, Any]:
        payload = action.model_dump()
        payload.pop("metadata", None)
        return payload

    def _parse_result(self, payload: dict[str, Any]) -> StepResult[ModernizationObservation]:
        observation = ModernizationObservation(**payload["observation"])
        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: dict[str, Any]) -> ModernizationState:
        return ModernizationState(**payload)
