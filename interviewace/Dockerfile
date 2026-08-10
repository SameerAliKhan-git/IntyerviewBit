FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /interviewace

# Build tooling is only needed while installing wheels, so it is removed in the same
# layer to keep it out of the final image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Requirements first, so dependency layers cache across source changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY app ./app

# Run unprivileged.
RUN useradd --create-home --uid 10001 interviewace \
    && chown -R interviewace:interviewace /interviewace
USER interviewace

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# app.main:app is the single canonical import path. Running from inside app/ would make
# `app` resolve as a namespace package and risk importing modules twice with split state.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --log-level info --ws-max-size 16777216 --timeout-keep-alive 300 --proxy-headers --forwarded-allow-ips '*'"]
