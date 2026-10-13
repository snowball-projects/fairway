# Proposal only. Build/review for the target architecture before deployment.
FROM python:3.12.14-slim-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir uv==0.12.15
WORKDIR /opt/fairway
COPY pyproject.toml uv.lock README.md LICENSE THIRD-PARTY-NOTICES.md ./
COPY src ./src
COPY data/catalog.json ./data/catalog.json
COPY scripts/catalog.py ./scripts/catalog.py
RUN python scripts/catalog.py export --output src/fairway/static/data
RUN uv sync --locked --no-dev --no-editable --python /usr/local/bin/python

FROM python:3.12.14-slim-bookworm
WORKDIR /opt/fairway
COPY --from=build /opt/fairway/.venv /opt/fairway/.venv
ENV PATH="/opt/fairway/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
    FAIRWAY_NATIONAL_BIND=0.0.0.0 \
    FAIRWAY_NATIONAL_ROUTER=http://valhalla:8002
USER 65532:65532
EXPOSE 8081
ENTRYPOINT ["fairway-national-api"]
