"""Typed models for the COBOL modernization OpenEnv environment."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from openenv.core.env_server.types import Action, Observation, State


Difficulty = Literal["easy", "medium", "hard"]
TaskType = Literal["extract", "compare", "fix"]


class RewardBreakdown(BaseModel):
    """Typed reward decomposition for deterministic grading."""

    completion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    improvement_bonus: float = Field(default=0.0, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    invalid_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    final_reward: float = Field(default=0.0, ge=0.0, le=1.0)


class ModernizationAction(Action):
    """Single submission action used for all three tasks."""

    task_id: str = Field(..., description="Task identifier, e.g. extract_easy.")
    program_mermaid: str = Field(
        default="",
        description="Mermaid program structure for extraction tasks.",
    )
    python_source: str = Field(
        default="",
        description="Python translation or repaired Python source.",
    )
    cobol_dependency_mermaid: str = Field(
        default="",
        description="Mermaid dependency graph for the COBOL program.",
    )
    python_dependency_mermaid: str = Field(
        default="",
        description="Mermaid dependency graph for the Python translation.",
    )
    fixed_mermaid: str = Field(
        default="",
        description="Updated Mermaid artifact for the hard auto-fix task.",
    )
    fixed_python_source: str = Field(
        default="",
        description="Updated Python source for the hard auto-fix task.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Optional agent notes about assumptions or repair strategy.",
    )


class ModernizationObservation(Observation):
    """Observation returned after reset and each step."""

    task_id: str = Field(..., description="Active task identifier.")
    title: str = Field(..., description="Short task title.")
    difficulty: Difficulty = Field(..., description="Task difficulty label.")
    task_type: TaskType = Field(..., description="Underlying grading mode.")
    objective: str = Field(..., description="Concrete task objective.")
    cobol_source: str = Field(..., description="The COBOL program being modernized.")
    attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=1, ge=1)
    best_score: float = Field(default=0.0, ge=0.0, le=1.0)
    feedback: list[str] = Field(
        default_factory=list,
        description="Deterministic grader feedback for the latest submission.",
    )
    required_fields: list[str] = Field(
        default_factory=list,
        description="Fields the agent should submit for this task.",
    )
    starter_artifacts: dict[str, Any] = Field(
        default_factory=dict,
        description="Broken or prior artifacts supplied to the agent.",
    )
    reward_breakdown: RewardBreakdown = Field(
        default_factory=RewardBreakdown,
        description="Detailed reward decomposition for the latest step.",
    )


class ModernizationState(State):
    """Persistent environment state for a single episode."""

    task_id: str = ""
    title: str = ""
    difficulty: Difficulty = "easy"
    task_type: TaskType = "extract"
    best_score: float = 0.0
    latest_score: float = 0.0
    latest_feedback: list[str] = Field(default_factory=list)
    max_attempts: int = 1
    last_submission_hash: str = ""
    baseline_extract_score: float = 0.0
    baseline_compare_score: float = 0.0
