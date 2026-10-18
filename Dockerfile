# Cross List web app. Data lives on a mounted disk at /data (SQLite database).
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"

WORKDIR /app
# Dependencies first so code changes rebuild quickly.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY rules ./rules
COPY data ./data

RUN useradd --create-home crosslist && mkdir -p /data && chown crosslist /data
USER crosslist

ENV CROSSLIST_DATABASE_URL=sqlite:////data/crosslist.db \
    CROSSLIST_DATA_DIR=/data \
    CROSSLIST_SEED_SYNTHETIC=false \
    CROSSLIST_LOAD_REAL_ON_START=true \
    PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
