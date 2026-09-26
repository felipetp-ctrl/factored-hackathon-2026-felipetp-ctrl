FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY tests/fixtures ./tests/fixtures
COPY demo_data ./demo_data
RUN uv sync --frozen --no-dev
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uv", "run", "--no-dev", "uvicorn", "dispute_ops.main:app", "--host", "0.0.0.0", "--port", "8000"]
