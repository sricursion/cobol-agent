"""Submission inference entrypoint with strict stdout logging."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from openai import OpenAI

from models import ModernizationAction
from server.cobol_modernization_environment import CobolModernizationEnvironment
from src.agent.config import Settings
from src.agent.mermaid import analyze_cobol_source, render_python_dependency_mermaid
from src.agent.openai_client import OpenAIWorkflowClient
from src.agent.schemas import (
    DependencyComparisonResult,
    GradeResult,
    MermaidExtractionResult,
)
from src.agent.task_catalog import TaskDefinition, get_task, list_tasks

LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME") or os.getenv("IMAGE_NAME")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL") or "https://api.openai.com/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or os.getenv("OPENAI_MODEL") or "o3"
BENCHMARK = os.getenv("BENCHMARK") or "cobol_modernization_env"
TASK_NAME = os.getenv("TASK_NAME")
MOCK_OPENAI = (os.getenv("MOCK_OPENAI") or "").strip().lower() in {"1", "true", "yes", "on"}

ZERO_GRADE = GradeResult(
    score=0.0,
    findings=[],
    risk_flags=[],
    confidence_reason="Initial baseline context.",
    metrics={},
)


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.2f} rewards={rewards_str}",
        flush=True,
    )


def build_settings() -> Settings:
    return Settings(
        openai_api_key=API_KEY,
        openai_base_url=API_BASE_URL,
        openai_model=MODEL_NAME,
        app_title="COBOL Conversion Agent",
        app_description="Submission inference runner.",
        mock_openai=MOCK_OPENAI or not bool(API_KEY),
        max_fix_rounds=1,
    )


def build_workflow() -> OpenAIWorkflowClient:
    client = (
        OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
        if API_KEY and not MOCK_OPENAI
        else None
    )
    return OpenAIWorkflowClient(build_settings(), client=client, model=MODEL_NAME)


def build_action(
    task: TaskDefinition,
    cobol_source: str,
    starter_artifacts: dict,
    workflow: OpenAIWorkflowClient,
) -> ModernizationAction:
    analysis = analyze_cobol_source(cobol_source)

    if task.task_type == "extract":
        extraction = workflow.extract_program_visual(cobol_source, analysis)
        return ModernizationAction(
            task_id=task.task_id,
            program_mermaid=extraction.program_mermaid,
            notes=extraction.extraction_notes,
        )

    if task.task_type == "compare":
        extraction = workflow.extract_program_visual(cobol_source, analysis)
        translation = workflow.translate_to_python(
            cobol_source,
            analysis,
            extraction,
            ZERO_GRADE,
        )
        comparison = workflow.compare_dependencies(
            cobol_source, analysis, translation, extraction
        )
        return ModernizationAction(
            task_id=task.task_id,
            python_source=comparison.python_source,
            cobol_dependency_mermaid=comparison.cobol_dependency_mermaid,
            python_dependency_mermaid=comparison.python_dependency_mermaid,
            notes=comparison.comparison_notes,
        )

    broken_extraction = MermaidExtractionResult(
        program_mermaid=starter_artifacts.get("broken_mermaid", ""),
        program_summary="Broken draft supplied for repair.",
        extraction_notes=["Starter artifact from environment reset."],
    )
    broken_comparison = DependencyComparisonResult(
        python_source=starter_artifacts.get("broken_python_source", ""),
        cobol_dependency_mermaid=starter_artifacts.get("broken_mermaid", ""),
        python_dependency_mermaid=render_python_dependency_mermaid(
            starter_artifacts.get("broken_python_source", ""),
            analysis.program_name,
        ),
        dependency_gaps=["Starter artifacts are intentionally incomplete."],
        comparison_notes=["Use grader feedback to improve these artifacts."],
    )
    fixed = workflow.auto_fix(
        cobol_source=cobol_source,
        extraction=broken_extraction,
        comparison=broken_comparison,
        extraction_grade=ZERO_GRADE,
        comparison_grade=ZERO_GRADE,
    )
    return ModernizationAction(
        task_id=task.task_id,
        fixed_mermaid=fixed.fixed_mermaid,
        fixed_python_source=fixed.fixed_python_source,
        notes=fixed.fix_summary,
    )


def summarize_action(action: ModernizationAction) -> str:
    payload = action.model_dump(exclude={"metadata", "notes", "task_id"})
    populated_fields = sorted(key for key, value in payload.items() if value)
    return f"submit(task_id={action.task_id},fields={'+'.join(populated_fields)})"


def run_task(task: TaskDefinition, workflow: OpenAIWorkflowClient) -> dict:
    env = CobolModernizationEnvironment()
    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=task.task_id, env=BENCHMARK, model=MODEL_NAME)

    try:
        observation = env.reset(task_id=task.task_id, seed=42)
        action = build_action(
            task=task,
            cobol_source=observation.cobol_source,
            starter_artifacts=observation.starter_artifacts,
            workflow=workflow,
        )
        result = env.step(action)
        reward = float(result.reward or 0.0)
        done = bool(result.done)
        rewards.append(reward)
        steps_taken = 1
        score = min(max(float(result.best_score), 0.0), 1.0)
        success = score >= task.success_threshold
        log_step(
            step=1,
            action=summarize_action(action),
            reward=reward,
            done=done,
            error=None,
        )
        return {
            "task_id": task.task_id,
            "score": score,
            "reward": reward,
            "success": success,
            "feedback": result.feedback,
        }
    finally:
        try:
            env.close()
        except Exception:
            pass
        log_end(success=success, steps=steps_taken, score=score, rewards=rewards)


def main() -> None:
    workflow = build_workflow()
    tasks = [get_task(TASK_NAME)] if TASK_NAME else list_tasks()
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    results = [run_task(task, workflow) for task in tasks]
    summary_path = output_dir / "inference_scores.json"
    summary_path.write_text(
        json.dumps(
            {
                "benchmark": BENCHMARK,
                "model": MODEL_NAME,
                "api_base_url": API_BASE_URL,
                "local_image_name": LOCAL_IMAGE_NAME,
                "results": results,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
