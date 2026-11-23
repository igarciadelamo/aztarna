FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY aztarna ./aztarna
RUN .venv/bin/python -c "from aztarna.astro import eph; eph()"

FROM python:3.13-slim
RUN useradd --create-home --uid 1000 app && mkdir /data && chown app /data
WORKDIR /app
COPY --from=build /app /app
ENV PATH=/app/.venv/bin:$PATH DATA_DIR=/data
USER app
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
# --no-access-log: no IP logs (privacy rule, PRODUCT.md §3).
CMD ["uvicorn", "aztarna.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
