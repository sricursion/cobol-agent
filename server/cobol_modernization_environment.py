"""OpenEnv environment for real-world COBOL modernization tasks."""

from __future__ import annotations

import hashlib
from typing import Any, Callable
from uuid import uuid4

from openenv.core.env_server import Environment

from models import (
    ModernizationAction,
    ModernizationObservation,
    ModernizationState,
    RewardBreakdown,
)
from openenv_envs.compare_eval_env import CompareEvalEnv
from openenv_envs.extract_eval_env import ExtractEvalEnv
from openenv_envs.fix_eval_env import FixEvalEnv
from src.agent.mermaid import analyze_cobol_source, render_python_dependency_mermaid
from src.agent.scoring import clamp_score
from src.agent.task_catalog import get_task, list_tasks


class CobolModernizationEnvironment(
    Environment[ModernizationAction, ModernizationObservation, ModernizationState]
):
    """Environment that simulates staged COBOL modernization work."""

    def __init__(self) -> None:
        super().__init__()
        self._extract_env = ExtractEvalEnv()
        self._compare_env = CompareEvalEnv()
        self._fix_env = FixEvalEnv()
        self._task = list_tasks()[0]
        self._state = ModernizationState(
            episode_id=str(uuid4()),
            task_id=self._task.task_id,
            title=self._task.title,
            difficulty=self._task.difficulty,
            task_type=self._task.task_type,
            max_attempts=self._task.max_attempts,
        )

    def reset(
        self,
        seed: int | None = None,
        episode_id: str | None = None,
        **kwargs: Any,
    ) -> ModernizationObservation:
        task_id = kwargs.get("task_id", list_tasks()[0].task_id)
        self._task = get_task(task_id)
        starter_artifacts = self._starter_artifacts()
        baseline_extract, baseline_compare = self._baseline_scores(starter_artifacts)

        self._state = ModernizationState(
            episode_id=episode_id or str(uuid4()),
            step_count=0,
            task_id=self._task.task_id,
            title=self._task.title,
            difficulty=self._task.difficulty,
            task_type=self._task.task_type,
            best_score=0.0,
            latest_score=0.0,
            latest_feedback=[],
            max_attempts=self._task.max_attempts,
            last_submission_hash="",
            baseline_extract_score=baseline_extract,
            baseline_compare_score=baseline_compare,
        )
        return ModernizationObservation(
            task_id=self._task.task_id,
            title=self._task.title,
            difficulty=self._task.difficulty,
            task_type=self._task.task_type,
            objective=self._task.objective,
            cobol_source=self._task.cobol_source,
            attempt=0,
            max_attempts=self._task.max_attempts,
            best_score=0.0,
            feedback=[
                f"Task ready: {self._task.title}",
                f"Difficulty: {self._task.difficulty}",
            ],
            required_fields=list(self._task.required_fields),
            starter_artifacts=starter_artifacts,
            reward_breakdown=RewardBreakdown(final_reward=0.0),
            reward=0.0,
            done=False,
            metadata={"seed": seed, "available_tasks": [task.task_id for task in list_tasks()]},
        )

    def step(
        self,
        action: ModernizationAction,
        timeout_s: float | None = None,
        **kwargs: Any,
    ) -> ModernizationObservation:
        del timeout_s, kwargs
        self._state.step_count += 1

        completion_score = self._completion_score(action)
        grade = self._grade_action(action)
        improvement_bonus = max(0.0, grade.score - self._state.best_score)
        submission_hash = self._submission_hash(action)
        repeat_penalty = 0.15 if submission_hash and submission_hash == self._state.last_submission_hash else 0.0
        invalid_penalty = min(0.30, 0.12 * len(grade.risk_flags))

        final_reward = clamp_score(
            (0.25 * completion_score)
            + (0.55 * grade.score)
            + (0.20 * improvement_bonus)
            - repeat_penalty
            - invalid_penalty
        )

        self._state.best_score = max(self._state.best_score, grade.score)
        self._state.latest_score = grade.score
        self._state.latest_feedback = grade.findings
        self._state.last_submission_hash = submission_hash

        done = (
            self._state.best_score >= self._task.success_threshold
            or self._state.step_count >= self._task.max_attempts
        )
        reward_breakdown = RewardBreakdown(
            completion_score=completion_score,
            quality_score=grade.score,
            improvement_bonus=improvement_bonus,
            repeat_penalty=repeat_penalty,
            invalid_penalty=invalid_penalty,
            final_reward=final_reward,
        )
        feedback = list(grade.findings)
        if grade.risk_flags:
            feedback.extend([f"Risk: {flag}" for flag in grade.risk_flags])

        return ModernizationObservation(
            task_id=self._task.task_id,
            title=self._task.title,
            difficulty=self._task.difficulty,
            task_type=self._task.task_type,
            objective=self._task.objective,
            cobol_source=self._task.cobol_source,
            attempt=self._state.step_count,
            max_attempts=self._task.max_attempts,
            best_score=self._state.best_score,
            feedback=feedback,
            required_fields=list(self._task.required_fields),
            starter_artifacts=self._starter_artifacts(),
            reward_breakdown=reward_breakdown,
            reward=final_reward,
            done=done,
            metadata={
                "task_score": grade.score,
                "success_threshold": self._task.success_threshold,
                "metrics": grade.metrics,
                "confidence_reason": grade.confidence_reason,
            },
        )

    @property
    def state(self) -> ModernizationState:
        return self._state

    def _starter_artifacts(self) -> dict[str, Any]:
        if self._task.task_type != "fix":
            return {}
        return {
            "broken_mermaid": self._task.broken_mermaid,
            "broken_python_source": self._task.broken_python_source,
        }

    def _baseline_scores(self, starter_artifacts: dict[str, Any]) -> tuple[float, float]:
        if self._task.task_type != "fix":
            return 0.0, 0.0
        analysis = analyze_cobol_source(self._task.cobol_source)
        extract_grade = self._extract_env.evaluate(
            self._task.cobol_source, starter_artifacts.get("broken_mermaid", "")
        )
        compare_grade = self._compare_env.evaluate(
            cobol_source=self._task.cobol_source,
            python_source=starter_artifacts.get("broken_python_source", ""),
            cobol_dependency_mermaid=starter_artifacts.get("broken_mermaid", ""),
            python_dependency_mermaid=render_python_dependency_mermaid(
                starter_artifacts.get("broken_python_source", ""), analysis.program_name
            ),
            dependency_gaps=["Starter artifacts are intentionally incomplete."],
        )
        return extract_grade.score, compare_grade.score

    def _completion_score(self, action: ModernizationAction) -> float:
        filled = 0
        for field_name in self._task.required_fields:
            if getattr(action, field_name, "").strip():
                filled += 1
        return clamp_score(filled / max(len(self._task.required_fields), 1))

    def _grade_action(self, action: ModernizationAction):
        graders: dict[str, Callable[[ModernizationAction], Any]] = {
            "extract": self._grade_extract,
            "compare": self._grade_compare,
            "fix": self._grade_fix,
        }
        return graders[self._task.task_type](action)

    def _grade_extract(self, action: ModernizationAction):
        return self._extract_env.evaluate(
            self._task.cobol_source,
            action.program_mermaid,
        )

    def _grade_compare(self, action: ModernizationAction):
        return self._compare_env.evaluate(
            cobol_source=self._task.cobol_source,
            python_source=action.python_source,
            cobol_dependency_mermaid=action.cobol_dependency_mermaid,
            python_dependency_mermaid=action.python_dependency_mermaid,
            dependency_gaps=[],
        )

    def _grade_fix(self, action: ModernizationAction):
        return self._fix_env.evaluate(
            cobol_source=self._task.cobol_source,
            fixed_python_source=action.fixed_python_source,
            fixed_mermaid=action.fixed_mermaid,
            previous_extract_score=self._state.baseline_extract_score,
            previous_compare_score=self._state.baseline_compare_score,
        )

    def _submission_hash(self, action: ModernizationAction) -> str:
        values = [getattr(action, field_name, "") for field_name in self._task.required_fields]
        serialized = "||".join(values).strip()
        if not serialized:
            return ""
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
