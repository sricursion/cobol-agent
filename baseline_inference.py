"""Reproducible baseline inference over the three OpenEnv tasks."""

from __future__ import annotations

import json
from pathlib import Path

from models import ModernizationAction
from openenv_envs.compare_eval_env import CompareEvalEnv
from openenv_envs.extract_eval_env import ExtractEvalEnv
from server.cobol_modernization_environment import CobolModernizationEnvironment
from src.agent.config import get_settings
from src.agent.mermaid import analyze_cobol_source, render_python_dependency_mermaid
from src.agent.openai_client import OpenAIWorkflowClient
from src.agent.schemas import DependencyComparisonResult, MermaidExtractionResult
from src.agent.task_catalog import list_tasks


def main() -> None:
    settings = get_settings()
    workflow = OpenAIWorkflowClient(settings)
    env = CobolModernizationEnvironment()
    extract_env = ExtractEvalEnv()
    compare_env = CompareEvalEnv()

    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    report_path = output_dir / "baseline_scores.json"

    results: list[dict] = []
    for task in list_tasks():
        observation = env.reset(task_id=task.task_id, seed=42)
        cobol_source = observation.cobol_source
        analysis = analyze_cobol_source(cobol_source)

        if task.task_type == "extract":
            extraction = workflow.extract_program_visual(cobol_source, analysis)
            action = ModernizationAction(
                task_id=task.task_id,
                program_mermaid=extraction.program_mermaid,
                notes=extraction.extraction_notes,
            )
        elif task.task_type == "compare":
            extraction = workflow.extract_program_visual(cobol_source, analysis)
            extraction_grade = extract_env.evaluate(cobol_source, extraction.program_mermaid)
            translation = workflow.translate_to_python(
                cobol_source, analysis, extraction, extraction_grade
            )
            comparison = workflow.compare_dependencies(
                cobol_source, analysis, translation, extraction
            )
            action = ModernizationAction(
                task_id=task.task_id,
                python_source=comparison.python_source,
                cobol_dependency_mermaid=comparison.cobol_dependency_mermaid,
                python_dependency_mermaid=comparison.python_dependency_mermaid,
                notes=comparison.comparison_notes,
            )
        else:
            starter = observation.starter_artifacts
            broken_extraction = MermaidExtractionResult(
                program_mermaid=starter.get("broken_mermaid", ""),
                program_summary="Broken draft supplied for repair.",
                extraction_notes=["Starter artifact from environment reset."],
            )
            broken_extract_grade = extract_env.evaluate(
                cobol_source, broken_extraction.program_mermaid
            )
            broken_comparison = DependencyComparisonResult(
                python_source=starter.get("broken_python_source", ""),
                cobol_dependency_mermaid=starter.get("broken_mermaid", ""),
                python_dependency_mermaid=render_python_dependency_mermaid(
                    starter.get("broken_python_source", ""), analysis.program_name
                ),
                dependency_gaps=["Starter artifacts are intentionally incomplete."],
                comparison_notes=["Use grader feedback to improve these artifacts."],
            )
            broken_compare_grade = compare_env.evaluate(
                cobol_source=cobol_source,
                python_source=broken_comparison.python_source,
                cobol_dependency_mermaid=broken_comparison.cobol_dependency_mermaid,
                python_dependency_mermaid=broken_comparison.python_dependency_mermaid,
                dependency_gaps=broken_comparison.dependency_gaps,
            )
            fixed = workflow.auto_fix(
                cobol_source=cobol_source,
                extraction=broken_extraction,
                comparison=broken_comparison,
                extraction_grade=broken_extract_grade,
                comparison_grade=broken_compare_grade,
            )
            action = ModernizationAction(
                task_id=task.task_id,
                fixed_mermaid=fixed.fixed_mermaid,
                fixed_python_source=fixed.fixed_python_source,
                notes=fixed.fix_summary,
            )

        final_observation = env.step(action)
        results.append(
            {
                "task_id": task.task_id,
                "difficulty": task.difficulty,
                "task_type": task.task_type,
                "reward": final_observation.reward,
                "best_score": final_observation.best_score,
                "attempt": final_observation.attempt,
                "feedback": final_observation.feedback,
                "reward_breakdown": final_observation.reward_breakdown.model_dump(),
                "used_mock_openai": workflow.using_mock_mode,
                "model": settings.openai_model,
            }
        )

    payload = {
        "model": settings.openai_model,
        "used_mock_openai": workflow.using_mock_mode,
        "results": results,
        "average_score": round(
            sum(item["best_score"] for item in results) / max(len(results), 1), 4
        ),
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
