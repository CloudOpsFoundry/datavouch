FROM ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d AS uv
FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_NO_PROGRESS=1
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --all-extras --no-install-project
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv build --wheel --no-build-isolation --offline \
    && UV_PROJECT_ENVIRONMENT=/opt/runtime uv sync --locked --all-extras --no-dev --no-install-project --offline \
    && uv pip install --python /opt/runtime/bin/python --no-index --no-deps dist/*.whl
FROM python:3.15.2-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9
ENV PATH=/opt/runtime/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
COPY --from=build /opt/runtime /opt/runtime
COPY examples /opt/datavouch/examples
WORKDIR /opt/datavouch
RUN mkdir /data && chown 10001:10001 /data && chmod 700 /data
USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8765), timeout=3).close()"
ENTRYPOINT ["python", "-m", "datavouch"]
CMD ["serve", "/opt/datavouch/examples/viewer.json", "--bind-address", "0.0.0.0", "--port", "8765"]
