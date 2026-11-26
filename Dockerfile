# syntax=docker/dockerfile:1
# The API image. It holds the app, the migrations and the data files, so the
# same image serves the API, applies migrations and runs `recipe-app db sync`.

FROM python:3.12-slim AS build
# The same uv version CI pins.
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependencies first, so a code change doesn't reinstall them.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.12-slim
RUN groupadd --system app && useradd --system --gid app --uid 10001 app
WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY data ./data
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    API_HOST=0.0.0.0
USER app
EXPOSE 8000
# Every limit (deadline, shutdown grace, keep-alive) comes from the settings
# (ADR-0013 rule 7). API_HOST is 0.0.0.0 here: the default, 127.0.0.1, is
# unreachable from outside the container.
CMD ["recipe-app", "serve"]
