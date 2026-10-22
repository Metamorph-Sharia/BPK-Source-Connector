# The BPK connector as a container, for the platform's Airflow (Metamorph-Knowledge-Platform/dags).
# Build from the workspace root, the directory holding every repository, so the contract package sits where
# pyproject.toml's path source expects it (../Metamorph-Knowledge-Platform/packages/metamorph-contract):
#   docker build -f BPK-Source-Connector/Dockerfile -t metamorph/bpk-connector:dev .
# data/ is not in the image: Airflow bind-mounts the repository's data/ directory at runtime.
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.27 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
# Bundles land in a named volume that takes this directory's owner the first time it is mounted.
RUN useradd --create-home --uid 1000 connector && mkdir /bundles && chown connector /bundles

WORKDIR /workspace/BPK-Source-Connector
COPY Metamorph-Knowledge-Platform/packages/metamorph-contract /workspace/Metamorph-Knowledge-Platform/packages/metamorph-contract
COPY Metamorph-Knowledge-Platform/packages/metamorph-pdf-text /workspace/Metamorph-Knowledge-Platform/packages/metamorph-pdf-text
COPY BPK-Source-Connector/pyproject.toml ./pyproject.toml
COPY BPK-Source-Connector/uv.lock ./uv.lock
COPY BPK-Source-Connector/README.md ./README.md
COPY BPK-Source-Connector/src ./src
COPY BPK-Source-Connector/config ./config
RUN uv sync --frozen --no-dev

USER connector
CMD ["bpk-connector", "--help"]
