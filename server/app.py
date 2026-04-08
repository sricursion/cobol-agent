"""FastAPI server for the COBOL modernization OpenEnv environment."""

from __future__ import annotations

from openenv.core.env_server import create_app

from models import ModernizationAction, ModernizationObservation
from server.cobol_modernization_environment import CobolModernizationEnvironment


app = create_app(
    CobolModernizationEnvironment,
    ModernizationAction,
    ModernizationObservation,
    env_name="cobol_modernization_env",
)


def main() -> None:
    """Run the environment server locally."""

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
