"""Gradio demo — COBOL Conversion Agent."""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path

import requests
import gradio as gr

from src.agent.config import get_settings
from src.agent.pipeline import CobolAgentPipeline
from src.agent.schemas import PipelineSnapshot


FIXTURE_DIR = Path("fixtures/core_batch")
_MERMAID_CACHE: dict[str, str] = {}   # cleared on every server restart


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_fixture(name: str) -> str:
    if not name or name == "None":
        return ""
    p = FIXTURE_DIR / f"{name}.cob"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _fixture_names() -> list[str]:
    if not FIXTURE_DIR.exists():
        return ["None"]
    return ["None"] + sorted(p.stem for p in FIXTURE_DIR.glob("*.cob"))


def _resolve_source(uploaded_file, pasted: str, fixture: str) -> str:
    if uploaded_file is not None:
        return Path(uploaded_file.name).read_text(encoding="utf-8")
    if pasted.strip():
        return pasted.strip()
    if fixture and fixture != "None":
        return _load_fixture(fixture)
    raise gr.Error("Provide COBOL source by upload, text box, or fixture picker.")


# ─────────────────────────────────────────────────────────────────────────────
# Score summary panel
# ─────────────────────────────────────────────────────────────────────────────

_TASK_META = [
    ("extract_easy", "Task 1 — Easy",   "Extract Mermaid structure from COBOL program"),
    ("compare_medium", "Task 2 — Medium", "Compare COBOL and Python dependency graphs"),
    ("fix_hard",    "Task 3 — Hard",    "Auto-fix broken Mermaid and Python translation"),
]


def _extract_score(grade_markdown: str) -> float | None:
    """Pull the numeric score out of a grade markdown string like 'Score: `0.78`'."""
    m = re.search(r"Score:\s*`?([0-9.]+)`?", grade_markdown)
    return float(m.group(1)) if m else None


def _score_bar(score: float) -> str:
    """Return a coloured progress bar HTML string."""
    pct = int(score * 100)
    if score >= 0.75:
        colour = "#22c55e"   # green
    elif score >= 0.50:
        colour = "#f59e0b"   # amber
    else:
        colour = "#ef4444"   # red
    return (
        f"<div style='background:#e5e7eb;border-radius:999px;height:8px;width:100%;margin-top:4px;'>"
        f"<div style='width:{pct}%;background:{colour};height:8px;border-radius:999px;'></div>"
        f"</div>"
    )


def _scores_html(g1: str, g2: str, g3: str) -> str:
    """Build the always-visible score summary strip."""
    grades = [g1, g2, g3]
    cards = []
    for (tid, label, explanation), grade_md in zip(_TASK_META, grades):
        score = _extract_score(grade_md)
        if score is None:
            score_display = "—"
            bar = ""
            score_colour = "#6b7280"
        else:
            score_display = f"{score:.2f}"
            bar = _score_bar(score)
            score_colour = "#22c55e" if score >= 0.75 else "#f59e0b" if score >= 0.50 else "#ef4444"

        cards.append(
            f"<div style='flex:1;background:#ffffff;border:1px solid #e5e7eb;"
            f"border-radius:10px;padding:14px 18px;min-width:200px;'>"
            f"<div style='font-size:11px;font-weight:600;color:#6b7280;"
            f"text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;'>{html.escape(label)}</div>"
            f"<div style='font-size:28px;font-weight:700;color:{score_colour};line-height:1;'>{score_display}</div>"
            f"{bar}"
            f"<div style='font-size:12px;color:#4b5563;margin-top:8px;'>{html.escape(explanation)}</div>"
            f"</div>"
        )

    return (
        "<div style='display:flex;gap:12px;flex-wrap:wrap;padding:4px 0;'>"
        + "".join(cards)
        + "</div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Server-side Mermaid → inline SVG
# ─────────────────────────────────────────────────────────────────────────────

_THEME_INIT = """\
%%{init: {
  "theme": "base",
  "themeVariables": {
    "primaryColor": "#bfdbfe",
    "primaryTextColor": "#000000",
    "primaryBorderColor": "#3b82f6",
    "lineColor": "#1f2937",
    "secondaryColor": "#d1fae5",
    "tertiaryColor": "#fef9c3",
    "background": "#ffffff",
    "mainBkg": "#bfdbfe",
    "nodeBorder": "#2563eb",
    "clusterBkg": "#f0f9ff",
    "titleColor": "#000000",
    "edgeLabelBackground": "#ffffff",
    "fontSize": "18px",
    "fontFamily": "Arial, sans-serif"
  }
}}%%
"""


def _normalize_svg(svg: str) -> str:
    """Make the SVG fill its container width at natural aspect ratio.

    The viewBox is kept intact so Mermaid's internal layout is preserved.
    We just set width=100% and remove any fixed pixel height so the browser
    scales the diagram to fit the panel while keeping all text readable.
    """
    svg = re.sub(r'\bwidth="[^"]*"',  'width="100%"', svg, count=1)
    svg = re.sub(r'\bheight="[^"]*"', 'height="auto"', svg, count=1)
    # Ensure the <svg> has a style that lets height follow the aspect ratio
    svg = svg.replace('<svg ', '<svg style="display:block;max-width:100%;" ', 1)
    return svg


def _fetch_svg(mermaid_source: str) -> str | None:
    if not mermaid_source.strip():
        return None
    if mermaid_source in _MERMAID_CACHE:
        return _MERMAID_CACHE[mermaid_source]
    try:
        themed = _THEME_INIT + mermaid_source.strip()
        encoded = base64.urlsafe_b64encode(themed.encode()).decode()
        resp = requests.get(f"https://mermaid.ink/svg/{encoded}", timeout=12)
        if resp.status_code == 200:
            svg = _normalize_svg(resp.text)
            _MERMAID_CACHE[mermaid_source] = svg
            return svg
    except Exception:
        pass
    return None


def _mermaid_panel(source: str, label: str) -> str:
    if not source.strip():
        return (
            f"<div style='padding:12px;color:#9ca3af;border:1px solid #e5e7eb;"
            f"border-radius:8px;font-size:13px;'>{html.escape(label)}: not yet generated</div>"
        )

    svg = _fetch_svg(source)

    if svg:
        safe_svg = svg.replace("<script", "<!-- script").replace("</script>", "</script -->")
        diagram_block = (
            f"<div style='background:#ffffff;border:1px solid #e5e7eb;border-radius:8px;"
            f"padding:12px;overflow-x:auto;overflow-y:hidden;'>{safe_svg}</div>"
        )
    else:
        diagram_block = (
            f"<div style='background:#fef3c7;border:1px solid #fbbf24;border-radius:8px;"
            f"padding:12px;color:#92400e;font-size:13px;'>"
            f"⚠ Diagram could not be rendered (mermaid.ink unreachable)"
            f"</div>"
        )

    return (
        f"<div style='border:1px solid #e5e7eb;border-radius:10px;padding:14px;"
        f"background:#f8fafc;margin-bottom:12px;'>"
        f"<div style='font-weight:700;font-size:15px;color:#1e3a5f;"
        f"margin-bottom:10px;'>{html.escape(label)}</div>"
        f"{diagram_block}"
        f"<details style='margin-top:10px;'>"
        f"<summary style='cursor:pointer;font-size:12px;color:#6b7280;'>Show Mermaid source</summary>"
        f"<pre style='background:#f1f5f9;color:#000000;padding:10px;border-radius:6px;"
        f"font-size:12px;overflow:auto;white-space:pre-wrap;max-height:220px;margin-top:6px;'>"
        f"{html.escape(source)}</pre>"
        f"</details></div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Side-by-side COBOL ↔ Python
# ─────────────────────────────────────────────────────────────────────────────

def _strip_mermaid_block(python_source: str) -> str:
    cleaned = re.sub(
        r'^PROGRAM_MERMAID\s*=\s*""".*?"""\s*\n?',
        "",
        python_source,
        flags=re.DOTALL | re.MULTILINE,
    )
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _comparison_html(cobol: str, python: str) -> str:
    if not cobol.strip() and not python.strip():
        return "<div style='color:#9ca3af;font-size:13px;padding:12px;'>Run the agent to see the comparison.</div>"

    python = _strip_mermaid_block(python)
    cobol_lines  = (cobol  or "").splitlines()
    python_lines = (python or "").splitlines()
    max_lines    = max(len(cobol_lines), len(python_lines), 1)

    rows = []
    for i in range(max_lines):
        cl = html.escape(cobol_lines[i])  if i < len(cobol_lines)  else ""
        pl = html.escape(python_lines[i]) if i < len(python_lines) else ""
        bg = "#f9fafb" if i % 2 == 0 else "#ffffff"
        n  = i + 1
        rows.append(
            f"<tr style='background:{bg};vertical-align:top;'>"
            # COBOL side
            f"<td style='width:32px;color:#9ca3af;font-size:11px;padding:3px 6px;"
            f"text-align:right;user-select:none;border-right:1px solid #e5e7eb;"
            f"font-family:monospace;'>{n}</td>"
            f"<td style='font-family:monospace;font-size:13px;padding:3px 10px;"
            f"white-space:pre;color:#1e3a5f;'>{cl}</td>"
            # Python side
            f"<td style='width:32px;color:#9ca3af;font-size:11px;padding:3px 6px;"
            f"text-align:right;user-select:none;border-right:1px solid #e5e7eb;"
            f"border-left:2px solid #d1d5db;font-family:monospace;'>{n}</td>"
            f"<td style='font-family:monospace;font-size:13px;padding:3px 10px;"
            f"white-space:pre;color:#14532d;'>{pl}</td>"
            f"</tr>"
        )

    header = (
        "<tr style='background:#f3f4f6;font-weight:700;font-size:13px;border-bottom:2px solid #e5e7eb;'>"
        "<td colspan='2' style='padding:8px 10px;color:#1e3a5f;border-right:2px solid #d1d5db;'>COBOL</td>"
        "<td colspan='2' style='padding:8px 10px;color:#14532d;'>Python</td>"
        "</tr>"
    )

    return (
        "<div style='overflow:auto;max-height:560px;border:1px solid #e5e7eb;"
        "border-radius:10px;background:#ffffff;'>"
        f"<table style='border-collapse:collapse;width:100%;'>{header}{''.join(rows)}</table>"
        "</div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gradio generator
# ─────────────────────────────────────────────────────────────────────────────

def _run(uploaded_file, pasted: str, fixture: str):
    settings = get_settings()
    pipeline = CobolAgentPipeline(settings)
    cobol_source = _resolve_source(uploaded_file, pasted, fixture)

    for snapshot in pipeline.run_stream(cobol_source):
        cobol  = snapshot.original_cobol_source or cobol_source
        python = snapshot.python_program_source or snapshot.fixed_python_source
        g1, g2, g3 = (
            snapshot.extraction_grade,
            snapshot.comparison_grade,
            snapshot.fix_grade if not snapshot.final_report_json
            else f"{snapshot.fix_grade}\n\n---\nSee **Report JSON** tab for full output.",
        )

        yield (
            snapshot.status_markdown,
            _scores_html(g1, g2, g3),          # always-visible score cards
            g1, g2, g3,                         # grading accordion detail
            _comparison_html(cobol, python),    # COBOL vs Python tab
            _mermaid_panel(snapshot.extraction_mermaid,       "Task 1 — COBOL program structure"),
            _mermaid_panel(snapshot.cobol_dependency_mermaid, "Task 2 — COBOL dependency graph"),
            _mermaid_panel(snapshot.python_dependency_mermaid,"Task 2 — Python dependency graph"),
            _mermaid_panel(snapshot.fixed_mermaid,            "Task 3 — Fixed diagram"),
            snapshot.final_report_json,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Gradio layout
# ─────────────────────────────────────────────────────────────────────────────

def build_demo() -> gr.Blocks:
    settings = get_settings()

    with gr.Blocks(title=settings.app_title) as demo:
        gr.Markdown(f"# {settings.app_title}")
        gr.Markdown(settings.app_description)

        # ── Input ────────────────────────────────────────────────────────────
        with gr.Row():
            with gr.Column(scale=2):
                cobol_input = gr.Textbox(
                    label="COBOL source",
                    lines=20,
                    placeholder="Paste COBOL here, or load a fixture.",
                )
            with gr.Column(scale=1):
                fixture_dd  = gr.Dropdown(choices=_fixture_names(), value="None",
                                          label="Fixture example")
                load_btn    = gr.Button("Load fixture")
                cobol_upload = gr.File(label="Upload .cob file",
                                       file_types=[".cob", ".cbl", ".txt"])
                run_btn     = gr.Button("▶  Run 3-task agent", variant="primary")
                status_md   = gr.Markdown("Pipeline status will appear here.")

        # ── Score summary (always visible) ───────────────────────────────────
        gr.Markdown("### Task scores")
        scores_html = gr.HTML(
            value=_scores_html("", "", ""),
            label="Scores",
        )

        # ── Grading detail (accordion) ────────────────────────────────────────
        with gr.Accordion("Full grading detail", open=False):
            with gr.Row():
                grade1 = gr.Markdown()
                grade2 = gr.Markdown()
                grade3 = gr.Markdown()

        # ── Output tabs ──────────────────────────────────────────────────────
        with gr.Tabs():
            with gr.Tab("↔  COBOL vs Python"):
                comparison_html = gr.HTML(
                    value="<div style='color:#9ca3af;padding:12px;'>Run the agent to see the comparison.</div>"
                )

            with gr.Tab("📊  Mermaid graphs"):
                mermaid1 = gr.HTML()
                with gr.Row():
                    mermaid2a = gr.HTML()
                    mermaid2b = gr.HTML()
                mermaid3 = gr.HTML()

            with gr.Tab("📄  Report JSON"):
                report_json = gr.Code(language="json", lines=30, interactive=False)

        # ── Wiring ────────────────────────────────────────────────────────────
        load_btn.click(_load_fixture, inputs=fixture_dd, outputs=cobol_input)
        run_btn.click(
            _run,
            inputs=[cobol_upload, cobol_input, fixture_dd],
            outputs=[
                status_md,
                scores_html,
                grade1, grade2, grade3,
                comparison_html,
                mermaid1, mermaid2a, mermaid2b, mermaid3,
                report_json,
            ],
        )

    return demo


demo = build_demo()

if __name__ == "__main__":
    demo.launch()
