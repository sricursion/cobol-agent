"""Structured data contracts for the COBOL conversion workflow."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictSchemaModel(BaseModel):
    """Shared base model for OpenAI structured outputs."""

    model_config = ConfigDict(extra="forbid")


class MermaidExtractionResult(StrictSchemaModel):
    """Task 1 result: program structure rendered as Mermaid."""

    program_mermaid: str = Field(
        ..., description="Mermaid flowchart that captures the COBOL program flow."
    )
    program_summary: str = Field(
        ..., description="Short natural-language summary of the COBOL program."
    )
    extraction_notes: list[str] = Field(
        default_factory=list,
        description="Assumptions or caveats made during Mermaid extraction.",
    )


class PythonTranslationResult(StrictSchemaModel):
    """Internal artifact used by later tasks."""

    python_source: str = Field(
        ..., description="Initial Python translation derived from the COBOL program."
    )
    translation_notes: list[str] = Field(
        default_factory=list,
        description="Notes about the translation strategy and any approximations.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Known simplifications or unsupported COBOL constructs.",
    )


class DependencyComparisonResult(StrictSchemaModel):
    """Task 2 result: dependency graphs and reconciliation notes."""

    python_source: str = Field(
        ..., description="Python source used to derive the dependency comparison."
    )
    cobol_dependency_mermaid: str = Field(
        ..., description="Mermaid dependency graph extracted from the COBOL program."
    )
    python_dependency_mermaid: str = Field(
        ..., description="Mermaid dependency graph extracted from the Python program."
    )
    dependency_gaps: list[str] = Field(
        default_factory=list,
        description="Human-readable gaps between COBOL and Python dependencies.",
    )
    comparison_notes: list[str] = Field(
        default_factory=list,
        description="Reasoning notes that explain the dependency comparison.",
    )


class AutoFixResult(StrictSchemaModel):
    """Task 3 result: improved artifacts after applying feedback."""

    fixed_python_source: str = Field(
        ..., description="Repaired Python translation after the auto-fix step."
    )
    fixed_mermaid: str = Field(
        ..., description="Updated Mermaid artifact after the auto-fix step."
    )
    fix_summary: list[str] = Field(
        default_factory=list,
        description="Summary of fixes attempted by the auto-fix agent.",
    )
    remaining_risks: list[str] = Field(
        default_factory=list,
        description="Known issues that remain after the fix pass.",
    )


class GradeResult(StrictSchemaModel):
    """Per-stage grade returned by an OpenEnv evaluator."""

    score: float = Field(..., ge=0.0, le=1.0)
    findings: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    confidence_reason: str = Field(
        ..., description="Short explanation for the assigned score."
    )
    metrics: dict[str, float] = Field(
        default_factory=dict,
        description="Low-level numeric metrics used when deriving the score.",
    )


class StageReport(StrictSchemaModel):
    """Report for a single task in the pipeline."""

    stage_name: str
    artifact: dict[str, Any]
    grade: GradeResult


class PipelineReport(StrictSchemaModel):
    """Persistable report returned to the UI."""

    source_hash: str
    program_summary: str
    extraction: MermaidExtractionResult
    comparison: DependencyComparisonResult
    auto_fix: AutoFixResult
    stage_reports: list[StageReport]
    final_score: float = Field(..., ge=0.0, le=1.0)
    final_summary: str


class PipelineSnapshot(StrictSchemaModel):
    """UI-friendly state emitted while the pipeline progresses."""

    status_markdown: str
    original_cobol_source: str = ""
    extraction_mermaid: str = ""
    extraction_grade: str = ""
    cobol_dependency_mermaid: str = ""
    python_dependency_mermaid: str = ""
    comparison_grade: str = ""
    python_program_source: str = ""
    fixed_mermaid: str = ""
    fixed_python_source: str = ""
    fix_grade: str = ""
    final_report_json: str = ""
