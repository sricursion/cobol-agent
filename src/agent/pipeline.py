"""Pipeline orchestration for the COBOL conversion workflow."""

from __future__ import annotations

import hashlib
import json
from typing import Iterator

from openenv_envs.compare_eval_env import CompareEvalEnv
from openenv_envs.extract_eval_env import ExtractEvalEnv
from openenv_envs.fix_eval_env import FixEvalEnv

from .config import Settings
from .mermaid import analyze_cobol_source
from .openai_client import OpenAIWorkflowClient
from .schemas import PipelineReport, PipelineSnapshot, StageReport
from .scoring import clamp_score


class CobolAgentPipeline:
    """Runs the three requested tasks and emits incremental UI snapshots."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.openai = OpenAIWorkflowClient(settings)
        self.extract_env = ExtractEvalEnv()
        self.compare_env = CompareEvalEnv()
        self.fix_env = FixEvalEnv()

    def run_stream(self, cobol_source: str) -> Iterator[PipelineSnapshot]:
        """Yield snapshots as each stage completes."""

        source_hash = hashlib.sha256(cobol_source.encode("utf-8")).hexdigest()[:12]
        analysis = analyze_cobol_source(cobol_source)
        mode_note = (
            "Mock mode is active because no OpenAI key was detected."
            if self.openai.using_mock_mode
            else f"Using OpenAI model `{self.settings.openai_model}`."
        )

        snapshot = PipelineSnapshot(
            status_markdown=(
                "### Pipeline started\n"
                f"- Source hash: `{source_hash}`\n"
                f"- Program: `{analysis.program_name}`\n"
                f"- {mode_note}"
            ),
            original_cobol_source=cobol_source,
        )
        yield snapshot

        extraction = self.openai.extract_program_visual(cobol_source, analysis)
        extraction_grade = self.extract_env.evaluate(
            cobol_source, extraction.program_mermaid
        )
        snapshot = snapshot.model_copy(
            update={
                "status_markdown": (
                    "### Task 1 complete\n"
                    "- Extracted Mermaid program structure\n"
                    f"- Score: `{extraction_grade.score:.2f}`"
                ),
                "extraction_mermaid": extraction.program_mermaid,
                "extraction_grade": _grade_markdown(extraction_grade),
            }
        )
        yield snapshot

        translation = self.openai.translate_to_python(
            cobol_source, analysis, extraction, extraction_grade
        )
        comparison = self.openai.compare_dependencies(
            cobol_source, analysis, translation, extraction
        )
        comparison_grade = self.compare_env.evaluate(
            cobol_source=cobol_source,
            python_source=comparison.python_source,
            cobol_dependency_mermaid=comparison.cobol_dependency_mermaid,
            python_dependency_mermaid=comparison.python_dependency_mermaid,
            dependency_gaps=comparison.dependency_gaps,
        )
        snapshot = snapshot.model_copy(
            update={
                "status_markdown": (
                    "### Task 2 complete\n"
                    "- Built COBOL/Python dependency graphs\n"
                    f"- Score: `{comparison_grade.score:.2f}`"
                ),
                "cobol_dependency_mermaid": comparison.cobol_dependency_mermaid,
                "python_dependency_mermaid": comparison.python_dependency_mermaid,
                "comparison_grade": _grade_markdown(
                    comparison_grade,
                    extra_lines=[
                        "Dependency gaps:",
                        *[f"- {gap}" for gap in comparison.dependency_gaps],
                    ],
                ),
                "python_program_source": comparison.python_source,
            }
        )
        yield snapshot

        auto_fix = self.openai.auto_fix(
            cobol_source=cobol_source,
            extraction=extraction,
            comparison=comparison,
            extraction_grade=extraction_grade,
            comparison_grade=comparison_grade,
        )
        fix_grade = self.fix_env.evaluate(
            cobol_source=cobol_source,
            fixed_python_source=auto_fix.fixed_python_source,
            fixed_mermaid=auto_fix.fixed_mermaid,
            previous_extract_score=extraction_grade.score,
            previous_compare_score=comparison_grade.score,
        )

        stage_reports = [
            StageReport(
                stage_name="extract",
                artifact=extraction.model_dump(),
                grade=extraction_grade,
            ),
            StageReport(
                stage_name="compare",
                artifact=comparison.model_dump(),
                grade=comparison_grade,
            ),
            StageReport(
                stage_name="auto_fix",
                artifact=auto_fix.model_dump(),
                grade=fix_grade,
            ),
        ]
        final_score = clamp_score(
            round(
                (
                    extraction_grade.score
                    + comparison_grade.score
                    + fix_grade.score
                )
                / 3,
                4,
            )
        )
        report = PipelineReport(
            source_hash=source_hash,
            program_summary=extraction.program_summary,
            extraction=extraction,
            comparison=comparison,
            auto_fix=auto_fix,
            stage_reports=stage_reports,
            final_score=final_score,
            final_summary=(
                f"Completed 3 tasks for {analysis.program_name}. Final score: "
                f"{final_score:.2f}. {'Mock mode was used.' if self.openai.using_mock_mode else 'OpenAI generation was used.'}"
            ),
        )

        snapshot = snapshot.model_copy(
            update={
                "status_markdown": (
                    "### Task 3 complete\n"
                    "- Auto-fix stage finished\n"
                    f"- Score: `{fix_grade.score:.2f}`\n\n"
                    f"### Final score\n`{report.final_score:.2f}`"
                ),
                "fixed_mermaid": auto_fix.fixed_mermaid,
                "python_program_source": auto_fix.fixed_python_source,
                "fixed_python_source": auto_fix.fixed_python_source,
                "fix_grade": _grade_markdown(
                    fix_grade,
                    extra_lines=["Fix summary:", *[f"- {item}" for item in auto_fix.fix_summary]],
                ),
                "final_report_json": json.dumps(
                    report.model_dump(mode="json"), indent=2
                ),
            }
        )
        yield snapshot


def _grade_markdown(grade, extra_lines: list[str] | None = None) -> str:
    lines = [f"Score: `{grade.score:.2f}`", "", "Findings:"]
    lines.extend([f"- {finding}" for finding in grade.findings] or ["- None"])
    if grade.risk_flags:
        lines.extend(["", "Risk flags:"])
        lines.extend([f"- {risk}" for risk in grade.risk_flags])
    lines.extend(["", f"Confidence reason: {grade.confidence_reason}"])
    if extra_lines:
        lines.extend(["", *extra_lines])
    return "\n".join(lines)
