"""OpenEnv evaluator for task 1 Mermaid extraction quality."""

from __future__ import annotations

from uuid import uuid4

from pydantic import Field

from openenv_envs._compat import Action, Observation, State
from src.agent.mermaid import extract_expected_signals, normalize_mermaid
from src.agent.scoring import clamp_score, ratio, weighted_score
from src.agent.schemas import GradeResult


class ExtractGradeAction(Action):
    """Action payload for grading a Mermaid extraction."""

    cobol_source: str
    candidate_mermaid: str


class ExtractGradeObservation(Observation):
    """Observation returned by the extraction evaluator."""

    findings: list[str] = Field(default_factory=list)
    missing_tokens: list[str] = Field(default_factory=list)
    covered_tokens: list[str] = Field(default_factory=list)


class ExtractEvalEnv:
    """Minimal OpenEnv-style environment for Mermaid extraction scoring."""

    def __init__(self) -> None:
        self._state = State(episode_id=str(uuid4()), step_count=0)

    def reset(self, **_: object) -> ExtractGradeObservation:
        self._state = State(episode_id=str(uuid4()), step_count=0)
        return ExtractGradeObservation(
            done=False,
            reward=0.0,
            findings=["Extraction evaluator ready."],
        )

    @property
    def state(self) -> State:
        return self._state

    def step(self, action: ExtractGradeAction) -> ExtractGradeObservation:
        self._state.step_count += 1
        expected = extract_expected_signals(action.cobol_source)["structural_tokens"]
        candidate = normalize_mermaid(action.candidate_mermaid)

        covered = sorted(
            token for token in expected if _token_present(token, candidate.nodes)
        )
        missing = sorted(token for token in expected if token not in covered)
        coverage = ratio(len(covered), len(expected))
        edge_density = 1.0 if candidate.edges else 0.2
        reward = clamp_score(weighted_score((coverage, 0.8), (edge_density, 0.2)))

        findings = [
            f"Covered {len(covered)} of {len(expected)} structural tokens.",
            f"Detected {len(candidate.edges)} Mermaid edge(s).",
        ]
        if missing:
            findings.append(f"Missing tokens: {', '.join(missing[:5])}")

        return ExtractGradeObservation(
            done=True,
            reward=reward,
            findings=findings,
            missing_tokens=missing,
            covered_tokens=covered,
            metadata={
                "coverage": coverage,
                "edge_density": edge_density,
            },
        )

    def evaluate(self, cobol_source: str, candidate_mermaid: str) -> GradeResult:
        observation = self.step(
            ExtractGradeAction(
                cobol_source=cobol_source,
                candidate_mermaid=candidate_mermaid,
            )
        )
        return GradeResult(
            score=clamp_score(
                float(observation.reward) if observation.reward is not None else 0.0
            ),
            findings=observation.findings,
            risk_flags=(
                ["Mermaid extraction missed structural tokens."]
                if observation.missing_tokens
                else []
            ),
            confidence_reason="Score is based on structural token coverage and graph edges.",
            metrics={
                "coverage": float(observation.metadata.get("coverage", 0.0)),
                "edge_density": float(observation.metadata.get("edge_density", 0.0)),
            },
        )


def _token_present(token: str, node_labels: set[str]) -> bool:
    upper = token.upper()
    return any(upper in label for label in node_labels)
