"""FastAPI server for the COBOL modernization OpenEnv environment.

On Hugging Face Spaces we want two things at once:
- the OpenEnv API endpoints (`/reset`, `/step`, `/state`, ...)
- the interactive Gradio demo at the Space homepage

This module builds the OpenEnv API first, then mounts the Gradio UI under `/`
so the homepage behaves like the demo while the benchmark endpoints stay live.
"""

from __future__ import annotations

import gradio as gr
from openenv.core.env_server import create_app

from app import build_demo
from models import ModernizationAction, ModernizationObservation
from server.cobol_modernization_environment import CobolModernizationEnvironment


api_app = create_app(
    CobolModernizationEnvironment,
    ModernizationAction,
    ModernizationObservation,
    env_name="cobol_modernization_env",
)

# Mount the demo at the Space root while preserving the existing API routes.
app = gr.mount_gradio_app(api_app, build_demo(), path="/")


def main() -> None:
    """Run the combined API + Gradio server locally."""

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
