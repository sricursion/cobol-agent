FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt pyproject.toml README.md openenv.yaml ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# HF Spaces routes external HTTPS traffic to the EXPOSE'd port.
# The OpenEnv FastAPI server exposes /reset, /step, /state on this port,
# satisfying the openenv validate ping. Run `python app.py` locally for the
# Gradio demo.
EXPOSE 7860

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "7860"]
