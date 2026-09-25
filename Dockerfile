# ---- base: dependencies shared by the test and runtime stages ----
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- test: runs the unit tests; the build fails if a test fails ----
FROM base AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY app/ app/
COPY tests/ tests/
RUN python -m pytest -q tests

# ---- runtime: the image that goes to Kubernetes (no test tools) ----
FROM base AS runtime
RUN useradd --system --uid 10001 appuser
COPY app/ app/
USER 10001
EXPOSE 8000
# 1 worker + threads keeps "requests served by this pod" as one counter per pod
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "app.app:app"]
