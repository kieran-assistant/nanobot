FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY nanobot/ nanobot/
COPY sql/ sql/
COPY repos/ repos/
COPY templates/ templates/
COPY tests/ tests/
COPY ARCHITECTURE.md .
COPY DATABASE_SCHEMA.md .
COPY README.md .

RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 5432

CMD ["python", "-m", "nanobot", "start"]
