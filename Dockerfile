FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system aix && adduser --system --ingroup aix aix

COPY pyproject.toml README.md LICENSE MANIFEST.in ./
COPY src ./src
COPY rubrics ./rubrics
COPY spec ./spec
COPY papers ./papers
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts/s3_restore_drill.py ./scripts/s3_restore_drill.py
RUN python -m pip install ".[platform]"

USER aix
EXPOSE 8000

CMD ["uvicorn", "aix_platform.main:app", "--host", "0.0.0.0", "--port", "8000"]
