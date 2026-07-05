FROM python:3.12-slim

# Pinned to the minor version used for local dev; bump deliberately.
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
# Cache mount: uv's download cache survives rebuilds, so lockfile changes
# only fetch what actually changed.
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

COPY . .

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py ingest_menu 24405.xml && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2"]
