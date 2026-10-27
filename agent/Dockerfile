# Heat Planner, for Cloud Run. Build context is this agent/ folder.
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY heat_planner ./heat_planner
COPY ui ./ui
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
ENV PORT=8080
CMD exec uvicorn heat_planner.api:app --host 0.0.0.0 --port ${PORT} --no-access-log
