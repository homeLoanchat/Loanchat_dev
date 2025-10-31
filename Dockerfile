# LoanBot 컨테이너 이미지 빌드용 Dockerfile

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# --- Builder stage: install Python dependencies into a virtualenv ---
FROM base AS builder

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# --- Runtime stage: slim runtime with prebuilt virtualenv ---
FROM base AS runtime

RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:${PATH}"

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . /app

ENV PORT=8000 \
    LOG_LEVEL=info \
    ENV=local

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
