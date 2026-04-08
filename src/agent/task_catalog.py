"""Task catalog for the OpenEnv COBOL modernization environment."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


FIXTURE_DIR = Path("fixtures/core_batch")

Difficulty = Literal["easy", "medium", "hard"]
TaskType = Literal["extract", "compare", "fix"]


@dataclass(frozen=True)
class TaskDefinition:
    """Definition of a single deterministic environment task."""

    task_id: str
    difficulty: Difficulty
    task_type: TaskType
    title: str
    objective: str
    cobol_fixture: str
    max_attempts: int
    success_threshold: float
    required_fields: tuple[str, ...]
    broken_python_source: str = ""
    broken_mermaid: str = ""

    @property
    def cobol_path(self) -> Path:
        return FIXTURE_DIR / f"{self.cobol_fixture}.cob"

    @property
    def expected_path(self) -> Path:
        return FIXTURE_DIR / f"{self.cobol_fixture}.expected.json"

    @property
    def cobol_source(self) -> str:
        return self.cobol_path.read_text(encoding="utf-8")

    @property
    def expected(self) -> dict:
        return json.loads(self.expected_path.read_text(encoding="utf-8"))


BROKEN_CLAIMS_MERMAID = """flowchart TD
    ClaimsAudit["CLAIMS-AUDIT"]
    Main["MAIN-PROCESS"]
    ClaimsAudit --> Main
"""

BROKEN_CLAIMS_PYTHON = """def main():
    total = 0
    print(total)
"""


TASKS: tuple[TaskDefinition, ...] = (
    TaskDefinition(
        task_id="extract_easy",
        difficulty="easy",
        task_type="extract",
        title="Extract COBOL program structure",
        objective=(
            "Create a Mermaid program map for a simple inventory update COBOL "
            "program. Preserve the main paragraphs and working-storage concepts."
        ),
        cobol_fixture="inventory_update",
        max_attempts=3,
        success_threshold=0.88,
        required_fields=("program_mermaid",),
    ),
    TaskDefinition(
        task_id="compare_medium",
        difficulty="medium",
        task_type="compare",
        title="Compare dependency graphs",
        objective=(
            "Compare COBOL and Python dependencies for a payroll report workflow. "
            "Return Mermaid dependency graphs for both systems and note the gaps."
        ),
        cobol_fixture="payroll_report",
        max_attempts=4,
        success_threshold=0.82,
        required_fields=(
            "python_source",
            "cobol_dependency_mermaid",
            "python_dependency_mermaid",
        ),
    ),
    TaskDefinition(
        task_id="fix_hard",
        difficulty="hard",
        task_type="fix",
        title="Repair a broken modernization draft",
        objective=(
            "Repair the Mermaid and Python artifacts for a claims audit COBOL "
            "program using grader feedback. The supplied draft is intentionally "
            "incomplete and should be improved, not replaced carelessly."
        ),
        cobol_fixture="claims_audit",
        max_attempts=5,
        success_threshold=0.86,
        required_fields=("fixed_mermaid", "fixed_python_source"),
        broken_python_source=BROKEN_CLAIMS_PYTHON,
        broken_mermaid=BROKEN_CLAIMS_MERMAID,
    ),
)


def get_task(task_id: str) -> TaskDefinition:
    """Return a task definition by id."""

    for task in TASKS:
        if task.task_id == task_id:
            return task
    raise KeyError(f"Unknown task_id: {task_id}")


def list_tasks() -> list[TaskDefinition]:
    """Return all task definitions in display order."""

    return list(TASKS)
