---
title: COBOL Conversion Agent
emoji: 🔄
colorFrom: blue
colorTo: indigo
sdk: docker
python_version: "3.10"
suggested_hardware: cpu-basic
---

# COBOL Conversion Agent

This project now contains two aligned surfaces for the same real-world task:

- A `Gradio` demo app in `app.py`
- A full `OpenEnv` environment with typed models, `reset()`, `step()`, `state`, `openenv.yaml`, and a FastAPI server in `server/`

The environment simulates a real modernization workflow humans actually do: reviewing and improving COBOL-to-Python migration artifacts.

## Real-World Task

The agent is placed in a COBOL modernization environment and must complete three concrete tasks:

1. `easy`: extract a Mermaid program map from a COBOL program
2. `medium`: compare COBOL and Python dependency graphs
3. `hard`: repair intentionally broken Mermaid and Python modernization drafts

Each task has a deterministic grader and returns reward in the `0.0` to `1.0` range.

## Stack

- `OpenAI Responses API` with structured outputs for extraction, comparison, translation, and repair
- `OpenEnv` for the environment contract and server/client shape
- Deterministic graders in `openenv_envs/`
- `Gradio` for the demo UI and Hugging Face Spaces deployment

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## OpenEnv Environment Setup

Run the environment server locally:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m openenv.cli.__main__ validate .
python -m server.app
```

Or use the package script once installed:

```bash
server
```

## Environment Variables

- `API_BASE_URL`: API endpoint for the LLM used by `inference.py`
- `MODEL_NAME`: model identifier used by `inference.py`
- `HF_TOKEN`: API key used by `inference.py`
- `OPENAI_API_KEY`: optional compatibility fallback for local demo use
- `OPENAI_MODEL`: optional compatibility fallback for local demo use
- `MOCK_OPENAI`: set to `1` to force deterministic local fallback behavior

If no `OPENAI_API_KEY` is present, the app still runs in mock mode so the UI and OpenEnv graders remain testable.

## Project Layout

- `app.py`: Gradio entrypoint
- `models.py`: typed OpenEnv action, observation, state, and reward models
- `client.py`: typed OpenEnv client
- `server/`: environment implementation and FastAPI server
- `src/agent/`: pipeline, schemas, OpenAI client, Mermaid helpers, scoring, task catalog
- `openenv_envs/`: deterministic task graders
- `fixtures/core_batch/`: COBOL task fixtures and expected signals
- `baseline_inference.py`: reproducible baseline runner across all three tasks
- `inference.py`: submission entrypoint with strict `[START]`, `[STEP]`, `[END]` stdout logs

## Action Space

The environment accepts a typed `ModernizationAction` with these main fields:

- `task_id`: active task identifier
- `program_mermaid`: used for the easy extraction task
- `python_source`: used for dependency comparison
- `cobol_dependency_mermaid`: COBOL dependency graph submission
- `python_dependency_mermaid`: Python dependency graph submission
- `fixed_mermaid`: repaired Mermaid artifact for the hard task
- `fixed_python_source`: repaired Python artifact for the hard task
- `notes`: optional agent notes

## Observation Space

The environment returns a typed `ModernizationObservation` with:

- task metadata: `task_id`, `title`, `difficulty`, `task_type`, `objective`
- source context: `cobol_source`
- progression: `attempt`, `max_attempts`, `best_score`
- grader output: `feedback`
- required submission fields: `required_fields`
- starter artifacts for repair tasks: `starter_artifacts`
- typed reward decomposition: `reward_breakdown`
- scalar OpenEnv fields: `reward`, `done`, `metadata`

## Reward Model

Rewards are meaningful over the full trajectory, not just binary at the end.

- `completion_score`: partial credit for filling required fields
- `quality_score`: deterministic grader score for the task
- `improvement_bonus`: reward for beating the best prior submission
- `repeat_penalty`: discourages identical repeated submissions
- `invalid_penalty`: penalizes risky or invalid artifacts

The final reward is clamped to `0.0` to `1.0`.

## Grading Notes

- `easy`: extraction quality is based on structural token coverage and Mermaid edges
- `medium`: dependency quality is based on expected dependency coverage and Python syntax validity
- `hard`: auto-fix quality is based on improvement over broken starter artifacts and residual syntax issues

All graders are deterministic and programmatic.

## Baseline Inference

Run the reproducible baseline across all 3 tasks:

```bash
python baseline_inference.py
```

This script:

- reads `OPENAI_API_KEY` and `OPENAI_MODEL` from the environment
- uses the OpenAI client when credentials are available
- falls back to deterministic mock mode if credentials are absent
- writes `outputs/baseline_scores.json`

## Submission Inference

The submission entrypoint is the required root file:

```bash
python inference.py
```

`inference.py`:

- uses the OpenAI client
- reads `API_BASE_URL`, `MODEL_NAME`, and `HF_TOKEN`
- emits strict stdout logs in the `[START]`, `[STEP]`, `[END]` format
- runs all three tasks by default
- writes `outputs/inference_scores.json`

## Validation

Validate the environment structure:

```bash
python -m openenv.cli.__main__ validate .
```

## Hugging Face Spaces

This repository is structured for a Gradio Space:

- `README.md` contains the Space metadata block.
- `app.py` is the default launch target.
- `requirements.txt` lists the runtime dependencies.

Store `OPENAI_API_KEY` as a Space secret before enabling live model calls.

## Docker

Two Docker paths are provided:

- `Dockerfile`: runs the Gradio demo app
- `server/Dockerfile`: runs the OpenEnv FastAPI server on port `8000`

Build the environment server image:

```bash
docker build -f server/Dockerfile -t cobol-modernization-env .
docker run -p 8000:8000 cobol-modernization-env
```

## DigitalOcean Later

This project is optimized for Hugging Face Spaces first. Once the workflow is stable, the same backend logic can be reused behind a service deployed on DigitalOcean.
