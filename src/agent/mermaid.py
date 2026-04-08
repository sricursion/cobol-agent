"""Helpers for extracting COBOL structure and normalizing Mermaid graphs."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field


DIVISION_RE = re.compile(r"^\s*([A-Z-]+)\s+DIVISION\.\s*$", re.IGNORECASE)
SECTION_RE = re.compile(r"^\s*([A-Z0-9-]+)\s+SECTION\.\s*$", re.IGNORECASE)
PARAGRAPH_RE = re.compile(r"^\s*([A-Z0-9-]+)\.\s*$", re.IGNORECASE)
VAR_RE = re.compile(r"^\s*(\d{2})\s+([A-Z0-9-]+)\b", re.IGNORECASE)
FD_RE = re.compile(r"^\s*FD\s+([A-Z0-9-]+)\b", re.IGNORECASE)
PROGRAM_ID_RE = re.compile(r"PROGRAM-ID\.\s+([A-Z0-9-]+)\.?", re.IGNORECASE)
PERFORM_RE = re.compile(r"\bPERFORM\s+([A-Z0-9-]+)", re.IGNORECASE)
CALL_RE = re.compile(r"\bCALL\s+['\"]?([A-Z0-9-]+)", re.IGNORECASE)
OPEN_RE = re.compile(r"\bOPEN\s+(INPUT|OUTPUT|I-O|EXTEND)\s+([A-Z0-9-]+)", re.IGNORECASE)
READ_RE = re.compile(r"\bREAD\s+([A-Z0-9-]+)", re.IGNORECASE)
WRITE_RE = re.compile(r"\bWRITE\s+([A-Z0-9-]+)", re.IGNORECASE)
DISPLAY_RE = re.compile(r"\bDISPLAY\b", re.IGNORECASE)


def sanitize_id(value: str) -> str:
    """Create a Mermaid-safe identifier from a free-form label."""

    value = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        return "node"
    if value[0].isdigit():
        value = f"n_{value}"
    return value


@dataclass
class CobolAnalysis:
    """Heuristic structure extracted from a COBOL source file."""

    program_name: str
    divisions: list[str] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    perform_edges: list[tuple[str, str]] = field(default_factory=list)
    file_edges: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class MermaidGraph:
    """Normalized Mermaid graph used by evaluators."""

    nodes: set[str] = field(default_factory=set)
    edges: set[tuple[str, str]] = field(default_factory=set)


def analyze_cobol_source(cobol_source: str) -> CobolAnalysis:
    """Extract high-value structural signals from a COBOL program."""

    program_name = "COBOLProgram"
    match = PROGRAM_ID_RE.search(cobol_source)
    if match:
        program_name = match.group(1).upper()

    analysis = CobolAnalysis(program_name=program_name)
    current_division: str | None = None
    current_section: str | None = None
    current_paragraph: str | None = None

    for raw_line in cobol_source.splitlines():
        line = raw_line.rstrip()

        division = DIVISION_RE.match(line)
        if division:
            current_division = division.group(1).upper()
            analysis.divisions.append(current_division)
            current_section = None
            current_paragraph = None
            continue

        section = SECTION_RE.match(line)
        if section:
            current_section = section.group(1).upper()
            analysis.sections.append(current_section)
            current_paragraph = None
            continue

        paragraph = PARAGRAPH_RE.match(line)
        if paragraph:
            name = paragraph.group(1).upper()
            if name.startswith("END-"):
                continue
            if name not in {*(analysis.divisions), *(analysis.sections)}:
                analysis.paragraphs.append(name)
                current_paragraph = name
            continue

        variable = VAR_RE.match(line)
        if variable and current_section == "WORKING-STORAGE":
            analysis.variables.append(variable.group(2).upper())

        fd = FD_RE.match(line)
        if fd:
            analysis.files.append(fd.group(1).upper())

        for pattern in (OPEN_RE, READ_RE, WRITE_RE):
            file_match = pattern.search(line)
            if not file_match:
                continue
            file_name = file_match.group(file_match.lastindex).upper()
            if file_name not in analysis.files:
                analysis.files.append(file_name)
            if current_paragraph:
                analysis.file_edges.append((current_paragraph, file_name))

        for perform in PERFORM_RE.findall(line):
            if current_paragraph:
                analysis.perform_edges.append((current_paragraph, perform.upper()))

        for call in CALL_RE.findall(line):
            analysis.calls.append(call.upper())

    analysis.divisions = _dedupe(analysis.divisions)
    analysis.sections = _dedupe(analysis.sections)
    analysis.paragraphs = _dedupe(analysis.paragraphs)
    analysis.variables = _dedupe(analysis.variables)
    analysis.files = _dedupe(analysis.files)
    analysis.calls = _dedupe(analysis.calls)
    analysis.perform_edges = list(dict.fromkeys(analysis.perform_edges))
    analysis.file_edges = list(dict.fromkeys(analysis.file_edges))
    return analysis


def render_program_mermaid(analysis: CobolAnalysis) -> str:
    """Render a Mermaid flowchart for the main COBOL program structure."""

    lines = ["flowchart TD"]
    root_id = sanitize_id(analysis.program_name)
    lines.append(f'    {root_id}["{analysis.program_name}"]')

    for division in analysis.divisions:
        division_id = sanitize_id(f"division_{division}")
        lines.append(f'    {division_id}["{division} DIVISION"]')
        lines.append(f"    {root_id} --> {division_id}")

    for section in analysis.sections:
        section_id = sanitize_id(f"section_{section}")
        lines.append(f'    {section_id}["{section} SECTION"]')
        lines.append(f"    {root_id} --> {section_id}")

    for paragraph in analysis.paragraphs:
        paragraph_id = sanitize_id(f"paragraph_{paragraph}")
        lines.append(f'    {paragraph_id}["{paragraph}"]')
        lines.append(f"    {root_id} --> {paragraph_id}")

    for source, target in analysis.perform_edges:
        lines.append(
            f"    {sanitize_id(f'paragraph_{source}')} --> "
            f"{sanitize_id(f'paragraph_{target}')}"
        )

    for paragraph, file_name in analysis.file_edges:
        file_id = sanitize_id(f"file_{file_name}")
        lines.append(f'    {file_id}["{file_name} FILE"]')
        lines.append(f"    {sanitize_id(f'paragraph_{paragraph}')} --> {file_id}")

    return "\n".join(_dedupe(lines))


def render_cobol_dependency_mermaid(analysis: CobolAnalysis) -> str:
    """Render a dependency graph for the COBOL program."""

    lines = ["flowchart LR"]
    program_id = sanitize_id(analysis.program_name)
    lines.append(f'    {program_id}["{analysis.program_name}"]')

    for paragraph in analysis.paragraphs:
        paragraph_id = sanitize_id(f"paragraph_{paragraph}")
        lines.append(f'    {paragraph_id}["{paragraph}"]')
        lines.append(f"    {program_id} --> {paragraph_id}")

    for variable in analysis.variables:
        variable_id = sanitize_id(f"var_{variable}")
        lines.append(f'    {variable_id}["{variable}"]')
        lines.append(f"    {program_id} --> {variable_id}")

    for file_name in analysis.files:
        file_id = sanitize_id(f"file_{file_name}")
        lines.append(f'    {file_id}["{file_name} FILE"]')
        lines.append(f"    {program_id} --> {file_id}")

    for call_name in analysis.calls:
        call_id = sanitize_id(f"call_{call_name}")
        lines.append(f'    {call_id}["CALL {call_name}"]')
        lines.append(f"    {program_id} --> {call_id}")

    for source, target in analysis.perform_edges:
        lines.append(
            f"    {sanitize_id(f'paragraph_{source}')} --> "
            f"{sanitize_id(f'paragraph_{target}')}"
        )

    for paragraph, file_name in analysis.file_edges:
        lines.append(
            f"    {sanitize_id(f'paragraph_{paragraph}')} --> "
            f"{sanitize_id(f'file_{file_name}')}"
        )

    return "\n".join(_dedupe(lines))


def render_python_dependency_mermaid(python_source: str, program_name: str) -> str:
    """Render a Mermaid dependency graph from a Python translation."""

    lines = ["flowchart LR"]
    program_id = sanitize_id(program_name)
    lines.append(f'    {program_id}["{program_name}"]')

    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        lines.append('    syntax_error["SYNTAX ERROR"]')
        lines.append(f"    {program_id} --> syntax_error")
        return "\n".join(lines)

    imports: set[str] = set()
    functions: set[str] = set()
    calls: set[str] = set()
    file_ops: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.FunctionDef):
            functions.add(node.name)
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name:
                calls.add(name)
                if name == "open":
                    file_ops.add("open")

    for import_name in sorted(imports):
        import_id = sanitize_id(f"import_{import_name}")
        lines.append(f'    {import_id}["import {import_name}"]')
        lines.append(f"    {program_id} --> {import_id}")

    for function_name in sorted(functions):
        function_id = sanitize_id(f"fn_{function_name}")
        lines.append(f'    {function_id}["{function_name}()"]')
        lines.append(f"    {program_id} --> {function_id}")

    for call_name in sorted(calls):
        call_id = sanitize_id(f"call_{call_name}")
        lines.append(f'    {call_id}["call {call_name}"]')
        lines.append(f"    {program_id} --> {call_id}")

    for op_name in sorted(file_ops):
        op_id = sanitize_id(f"fileop_{op_name}")
        lines.append(f'    {op_id}["file {op_name}"]')
        lines.append(f"    {program_id} --> {op_id}")

    return "\n".join(_dedupe(lines))


def normalize_mermaid(mermaid_source: str) -> MermaidGraph:
    """Parse Mermaid graph text into normalized nodes and edges."""

    graph = MermaidGraph()
    node_pattern = re.compile(r'^\s*([A-Za-z0-9_]+)\s*\["([^"]+)"\]')
    edge_pattern = re.compile(r"([A-Za-z0-9_]+)\s*-->\s*([A-Za-z0-9_]+)")

    for raw_line in mermaid_source.splitlines():
        line = raw_line.strip()
        node_match = node_pattern.match(line)
        if node_match:
            graph.nodes.add(node_match.group(2).strip().upper())

        for edge in edge_pattern.finditer(line):
            graph.edges.add((edge.group(1).upper(), edge.group(2).upper()))

    return graph


def extract_expected_signals(cobol_source: str) -> dict[str, set[str]]:
    """Build simple expected signal sets for grading heuristics."""

    analysis = analyze_cobol_source(cobol_source)
    tokens = {analysis.program_name.upper()}
    tokens.update(analysis.divisions)
    tokens.update(analysis.sections)
    tokens.update(analysis.paragraphs)
    tokens.update(analysis.variables)
    tokens.update(analysis.files)
    return {
        "structural_tokens": tokens,
        "paragraphs": set(analysis.paragraphs),
        "files": set(analysis.files),
        "variables": set(analysis.variables),
    }


def fallback_python_translation(
    cobol_source: str, analysis: CobolAnalysis, program_mermaid: str
) -> str:
    """Create a deterministic Python translation for offline or mock mode."""

    lines = [
        f'"""Generated from COBOL program {analysis.program_name}."""',
        "",
        f'PROGRAM_MERMAID = """{program_mermaid}"""',
        "",
    ]

    if analysis.files:
        lines.append(f"FILES = {analysis.files!r}")
        lines.append("")

    paragraphs = analysis.paragraphs or ["MAIN-PROCEDURE"]
    for paragraph in paragraphs:
        func_name = sanitize_id(paragraph.lower())
        lines.append(f"def {func_name}(state: dict) -> None:")
        lines.append(f'    """Approximation of COBOL paragraph {paragraph}."""')
        lines.append("    return None")
        lines.append("")

    main_function = sanitize_id(paragraphs[0].lower())
    lines.append("def main() -> None:")
    lines.append("    state: dict = {}")
    lines.append(f"    {main_function}(state)")
    if DISPLAY_RE.search(cobol_source):
        lines.append('    print("Translation completed")')
    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    main()")
    return "\n".join(lines)


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
