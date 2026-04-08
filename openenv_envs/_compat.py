"""Compatibility layer for importing OpenEnv base models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

try:  # pragma: no branch
    from openenv.core.env_server.types import Action, Observation, State
except ImportError:  # pragma: no cover - fallback for static inspection only
    class Action(BaseModel):
        metadata: dict[str, Any] = Field(default_factory=dict)

    class Observation(BaseModel):
        done: bool = False
        reward: float | None = None
        metadata: dict[str, Any] = Field(default_factory=dict)

    class State(BaseModel):
        episode_id: str | None = None
        step_count: int = 0
