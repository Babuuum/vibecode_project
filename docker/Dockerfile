FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_HOME="/opt/poetry" \
    PATH="$POETRY_HOME/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://install.python-poetry.org | python3 -

COPY pyproject.toml README.md ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-root --only main

COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations

CMD ["uvicorn", "src.autocontent.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
