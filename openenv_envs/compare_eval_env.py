"""OpenEnv evaluator for dependency comparison quality."""

from __future__ import annotations

import ast
from uuid import uuid4

from pydantic import Field

from openenv_envs._compat import Action, Observation, State
from src.agent.mermaid import analyze_cobol_source, normalize_mermaid
from src.agent.scoring import clamp_score, ratio, weighted_score
from src.agent.schemas import GradeResult


class CompareGradeAction(Action):
    """Action payload for grading dependency comparison artifacts."""

    cobol_source: str
    python_source: str
    cobol_dependency_mermaid: str
    python_dependency_mermaid: str
    dependency_gaps: list[str] = Field(default_factory=list)


class CompareGradeObservation(Observation):
    """Observation returned by the dependency comparison evaluator."""

    findings: list[str] = Field(default_factory=list)
    missing_dependencies: list[str] = Field(default_factory=list)
    syntax_valid: bool = True


class CompareEvalEnv:
    """Environment that scores how well Python dependencies reflect COBOL ones."""

    def __init__(self) -> None:
        self._state = State(episode_id=str(uuid4()), step_count=0)

    def reset(self, **_: object) -> CompareGradeObservation:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        return CompareGradeObservation(
            done=False,
            reward=0.0,
            findings=["Dependency comparison evaluator ready."],
        )

    @property
    def state(self) -> State:
        return self._state

    def step(self, action: CompareGradeAction) -> CompareGradeObservation:
        self._state.step_count += 1
        analysis = analyze_cobol_source(action.cobol_source)
        expected_dependencies = {
            *analysis.paragraphs,
            *analysis.files,
            *analysis.calls,
        }
        cobol_graph = normalize_mermaid(action.cobol_dependency_mermaid)
        python_graph = normalize_mermaid(action.python_dependency_mermaid)

        represented_in_cobol_graph = {
            token
            for token in expected_dependencies
            if _token_present(token, cobol_graph.nodes)
        }
        represented_in_python_graph = {
            token
            for token in expected_dependencies
            if _token_present(token, python_graph.nodes)
        }
        coverage = ratio(len(represented_in_python_graph), len(expected_dependencies))
        cobol_graph_quality = ratio(
            len(represented_in_cobol_graph), len(expected_dependencies)
        )

        syntax_valid = True
        syntax_error = ""
        try:
            ast.parse(action.python_source)
        except SyntaxError as exc:
            syntax_valid = False
            syntax_error = str(exc)

        gap_bonus = 0.9 if action.dependency_gaps else 0.6
        syntax_component = 1.0 if syntax_valid else 0.1
        reward = clamp_score(
            weighted_score(
                (coverage, 0.5),
                (cobol_graph_quality, 0.2),
                (gap_bonus, 0.1),
                (syntax_component, 0.2),
            )
        )

        missing = sorted(expected_dependencies.difference(represented_in_python_graph))
        findings = [
            f"Python dependency graph covers {len(represented_in_python_graph)} of "
            f"{len(expected_dependencies)} expected dependency token(s).",
            f"COBOL dependency graph covers {len(represented_in_cobol_graph)} of "
            f"{len(expected_dependencies)} expected dependency token(s).",
        ]
        if action.dependency_gaps:
            findings.append(
                f"Comparison produced {len(action.dependency_gaps)} explicit gap note(s)."
            )
        if not syntax_valid:
            findings.append(f"Python syntax issue detected: {syntax_error}")

        return CompareGradeObservation(
            done=True,
            reward=reward,
            findings=findings,
            missing_dependencies=missing,
            syntax_valid=syntax_valid,
            metadata={
                "coverage": coverage,
                "cobol_graph_quality": cobol_graph_quality,
                "syntax_valid": syntax_valid,
            },
        )

    def evaluate(
        self,
        cobol_source: str,
        python_source: str,
        cobol_dependency_mermaid: str,
        python_dependency_mermaid: str,
        dependency_gaps: list[str],
    ) -> GradeResult:
        observation = self.step(
            CompareGradeAction(
                cobol_source=cobol_source,
                python_source=python_source,
                cobol_dependency_mermaid=cobol_dependency_mermaid,
                python_dependency_mermaid=python_dependency_mermaid,
                dependency_gaps=dependency_gaps,
            )
        )
        risks = list(observation.missing_dependencies)
        if not observation.syntax_valid:
            risks.append("Python translation is not syntactically valid.")
        return GradeResult(
            score=clamp_score(
                float(observation.reward) if observation.reward is not None else 0.0
            ),
            findings=observation.findings,
            risk_flags=risks,
            confidence_reason=(
                "Score is based on dependency coverage, reported gaps, and Python syntax."
            ),
            metrics={
                "coverage": float(observation.metadata.get("coverage", 0.0)),
                "cobol_graph_quality": float(
                    observation.metadata.get("cobol_graph_quality", 0.0)
                ),
                "syntax_valid": 1.0
                if bool(observation.metadata.get("syntax_valid", False))
                else 0.0,
            },
        )


def _token_present(token: str, node_labels: set[str]) -> bool:
    upper = token.upper()
    return any(upper in label for label in node_labels)
