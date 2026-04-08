"""OpenEnv evaluator for the auto-fix stage."""

from __future__ import annotations

import ast
from uuid import uuid4

from pydantic import Field

from openenv_envs._compat import Action, Observation, State
from openenv_envs.compare_eval_env import CompareEvalEnv
from openenv_envs.extract_eval_env import ExtractEvalEnv
from src.agent.mermaid import analyze_cobol_source, render_python_dependency_mermaid
from src.agent.scoring import clamp_score, weighted_score
from src.agent.schemas import GradeResult


class FixGradeAction(Action):
    """Action payload for grading the auto-fix stage."""

    cobol_source: str
    fixed_python_source: str
    fixed_mermaid: str
    previous_extract_score: float
    previous_compare_score: float


class FixGradeObservation(Observation):
    """Observation returned by the auto-fix evaluator."""

    findings: list[str] = Field(default_factory=list)
    improved: bool = False
    syntax_valid: bool = True


class FixEvalEnv:
    """Environment that checks whether the auto-fix stage improved results."""

    def __init__(self) -> None:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._extract_env = ExtractEvalEnv()
        self._compare_env = CompareEvalEnv()

    def reset(self, **_: object) -> FixGradeObservation:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        return FixGradeObservation(
            done=False,
            reward=0.0,
            findings=["Auto-fix evaluator ready."],
        )

    @property
    def state(self) -> State:
        return self._state

    def step(self, action: FixGradeAction) -> FixGradeObservation:
        self._state.step_count += 1
        analysis = analyze_cobol_source(action.cobol_source)

        extract_grade = self._extract_env.evaluate(
            action.cobol_source, action.fixed_mermaid
        )
        compare_grade = self._compare_env.evaluate(
            cobol_source=action.cobol_source,
            python_source=action.fixed_python_source,
            cobol_dependency_mermaid=action.fixed_mermaid,
            python_dependency_mermaid=render_python_dependency_mermaid(
                action.fixed_python_source, analysis.program_name
            ),
            dependency_gaps=[],
        )

        syntax_valid = True
        try:
            ast.parse(action.fixed_python_source)
        except SyntaxError:
            syntax_valid = False

        improved = (
            extract_grade.score >= action.previous_extract_score
            and compare_grade.score >= action.previous_compare_score
        )
        reward = clamp_score(
            weighted_score(
                (extract_grade.score, 0.35),
                (compare_grade.score, 0.45),
                (1.0 if syntax_valid else 0.1, 0.20),
            )
        )
        findings = [
            f"Extraction score moved from {action.previous_extract_score:.2f} "
            f"to {extract_grade.score:.2f}.",
            f"Comparison score moved from {action.previous_compare_score:.2f} "
            f"to {compare_grade.score:.2f}.",
        ]
        if syntax_valid:
            findings.append("Fixed Python source parses successfully.")
        else:
            findings.append("Fixed Python source still contains syntax errors.")

        return FixGradeObservation(
            done=True,
            reward=reward,
            findings=findings,
            improved=improved,
            syntax_valid=syntax_valid,
            metadata={
                "extract_score": extract_grade.score,
                "compare_score": compare_grade.score,
                "improved": improved,
                "syntax_valid": syntax_valid,
            },
        )

    def evaluate(
        self,
        cobol_source: str,
        fixed_python_source: str,
        fixed_mermaid: str,
        previous_extract_score: float,
        previous_compare_score: float,
    ) -> GradeResult:
        observation = self.step(
            FixGradeAction(
                cobol_source=cobol_source,
                fixed_python_source=fixed_python_source,
                fixed_mermaid=fixed_mermaid,
                previous_extract_score=previous_extract_score,
                previous_compare_score=previous_compare_score,
            )
        )
        risks: list[str] = []
        if not observation.improved:
            risks.append("Auto-fix did not improve every earlier stage score.")
        if not observation.syntax_valid:
            risks.append("Fixed Python source is not syntactically valid.")
        return GradeResult(
            score=clamp_score(
                float(observation.reward) if observation.reward is not None else 0.0
            ),
            findings=observation.findings,
            risk_flags=risks,
            confidence_reason=(
                "Score is based on post-fix extraction quality, dependency quality, "
                "and Python syntax."
            ),
            metrics={
                "extract_score": float(observation.metadata.get("extract_score", 0.0)),
                "compare_score": float(observation.metadata.get("compare_score", 0.0)),
                "improved": 1.0 if bool(observation.metadata.get("improved", False)) else 0.0,
                "syntax_valid": 1.0
                if bool(observation.metadata.get("syntax_valid", False))
                else 0.0,
            },
        )
