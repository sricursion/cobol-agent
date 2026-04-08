"""OpenAI-backed generation helpers with structured-output fallbacks."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from .config import Settings
from .mermaid import (
    CobolAnalysis,
    fallback_python_translation,
    render_cobol_dependency_mermaid,
    render_program_mermaid,
    render_python_dependency_mermaid,
)
from .schemas import (
    AutoFixResult,
    DependencyComparisonResult,
    GradeResult,
    MermaidExtractionResult,
    PythonTranslationResult,
)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - import guard for static inspection
    OpenAI = None  # type: ignore[assignment]


StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class OpenAIWorkflowClient:
    """Thin wrapper around structured OpenAI Responses API calls."""

    def __init__(self, settings: Settings, client: OpenAI | None = None, model: str | None = None):
        self.settings = settings
        self._model = model or settings.openai_model
        self._client = client
        if self._client is None:
            self._client = (
                OpenAI(
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                )
                if OpenAI and settings.openai_api_key and not settings.mock_openai
                else None
            )

    @property
    def using_mock_mode(self) -> bool:
        """Whether the workflow is using deterministic local fallbacks."""

        return self._client is None

    def extract_program_visual(self, cobol_source: str, analysis: CobolAnalysis) -> MermaidExtractionResult:
        """Task 1: generate the Mermaid program structure."""

        fallback = MermaidExtractionResult(
            program_mermaid=render_program_mermaid(analysis),
            program_summary=(
                f"{analysis.program_name} has {len(analysis.paragraphs)} paragraph(s), "
                f"{len(analysis.files)} file dependency(ies), and "
                f"{len(analysis.variables)} working-storage variable(s)."
            ),
            extraction_notes=[
                "Deterministic fallback extraction was used.",
                "Review the Mermaid output before treating it as canonical.",
            ],
        )

        prompt = (
            "Extract a Mermaid flowchart from the COBOL program. Use a compact "
            "flowchart TD graph, keep node labels readable, and summarize the "
            "program behavior. If the source is incomplete, mention assumptions."
        )
        return self._structured_or_fallback(
            schema=MermaidExtractionResult,
            prompt=prompt,
            user_payload={
                "cobol_source": cobol_source,
                "analysis_hints": analysis.__dict__,
            },
            fallback=fallback,
        )

    def translate_to_python(
        self,
        cobol_source: str,
        analysis: CobolAnalysis,
        extraction: MermaidExtractionResult,
        extraction_grade: GradeResult,
    ) -> PythonTranslationResult:
        """Internal translation step used before dependency comparison."""

        fallback_source = fallback_python_translation(
            cobol_source, analysis, extraction.program_mermaid
        )
        fallback = PythonTranslationResult(
            python_source=fallback_source,
            translation_notes=[
                "Deterministic fallback translation was used.",
                "The translation preserves paragraph boundaries as Python functions.",
            ],
            assumptions=[
                "Complex COBOL control flow is approximated.",
                "File handling remains conceptual in fallback mode.",
            ],
        )
        prompt = (
            "Translate the COBOL program into readable Python. Keep the code "
            "simple, preserve main paragraph structure, and make dependencies "
            "explicit enough for later Mermaid graph extraction."
        )
        return self._structured_or_fallback(
            schema=PythonTranslationResult,
            prompt=prompt,
            user_payload={
                "cobol_source": cobol_source,
                "program_mermaid": extraction.program_mermaid,
                "extraction_grade": extraction_grade.model_dump(),
            },
            fallback=fallback,
        )

    def compare_dependencies(
        self,
        cobol_source: str,
        analysis: CobolAnalysis,
        translation: PythonTranslationResult,
        extraction: MermaidExtractionResult,
    ) -> DependencyComparisonResult:
        """Task 2: compare COBOL and Python dependency graphs."""

        fallback_cobol_graph = render_cobol_dependency_mermaid(analysis)
        fallback_python_graph = render_python_dependency_mermaid(
            translation.python_source, analysis.program_name
        )
        fallback = DependencyComparisonResult(
            python_source=translation.python_source,
            cobol_dependency_mermaid=fallback_cobol_graph,
            python_dependency_mermaid=fallback_python_graph,
            dependency_gaps=[
                "File and paragraph dependencies are heuristic when mock mode is active.",
            ],
            comparison_notes=[
                "Fallback comparison uses local COBOL and Python parsers.",
                f"Program Mermaid from task 1 was available: {bool(extraction.program_mermaid)}.",
            ],
        )
        prompt = (
            "Compare the COBOL program dependencies against the generated Python "
            "program. Return Mermaid dependency graphs for both, include the "
            "Python source that was analyzed, and identify missing or mismatched "
            "dependencies in plain English."
        )
        return self._structured_or_fallback(
            schema=DependencyComparisonResult,
            prompt=prompt,
            user_payload={
                "cobol_source": cobol_source,
                "analysis_hints": analysis.__dict__,
                "program_mermaid": extraction.program_mermaid,
                "python_source": translation.python_source,
            },
            fallback=fallback,
        )

    def auto_fix(
        self,
        cobol_source: str,
        extraction: MermaidExtractionResult,
        comparison: DependencyComparisonResult,
        extraction_grade: GradeResult,
        comparison_grade: GradeResult,
    ) -> AutoFixResult:
        """Task 3: repair the generated artifacts using earlier feedback."""

        fallback = AutoFixResult(
            fixed_python_source=comparison.python_source,
            fixed_mermaid=extraction.program_mermaid,
            fix_summary=[
                "Fallback auto-fix kept the best available artifacts unchanged.",
                "Use a live OpenAI key to enable repair suggestions.",
            ],
            remaining_risks=[
                "Dependency gaps may still exist in the Python translation.",
                "The Mermaid output may omit COBOL edge cases.",
            ],
        )
        prompt = (
            "Act as an auto-fix agent. Improve the Python translation and Mermaid "
            "diagram using the grading findings from earlier stages. Keep the "
            "result conservative and explain any remaining risks."
        )
        return self._structured_or_fallback(
            schema=AutoFixResult,
            prompt=prompt,
            user_payload={
                "cobol_source": cobol_source,
                "extraction": extraction.model_dump(),
                "comparison": comparison.model_dump(),
                "extraction_grade": extraction_grade.model_dump(),
                "comparison_grade": comparison_grade.model_dump(),
            },
            fallback=fallback,
        )

    def _structured_or_fallback(
        self,
        schema: type[StructuredModel],
        prompt: str,
        user_payload: dict,
        fallback: StructuredModel,
    ) -> StructuredModel:
        if self._client is None:
            return fallback

        system_msg = {
            "role": "system",
            "content": (
                "You are a COBOL modernization assistant. "
                "Always return valid JSON that matches the schema exactly. "
                "Do not add any text outside the JSON object."
            ),
        }
        user_msg = {
            "role": "user",
            "content": f"{prompt}\n\n{json.dumps(user_payload, indent=2)}",
        }

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[system_msg, user_msg],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                },
            )
        except Exception:
            return fallback

        choice = response.choices[0] if response.choices else None
        if choice is None:
            return fallback
        if getattr(choice.message, "refusal", None):
            return fallback

        content = (choice.message.content or "").strip()
        if not content:
            return fallback

        try:
            return schema.model_validate(json.loads(content))
        except Exception:
            return fallback
