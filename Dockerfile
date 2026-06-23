# syntax=docker/dockerfile:1.7
# ---- Builder ----------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Install only the optional runtime deps (msal / requests) into a venv so the
# final image stays tiny.
COPY requirements.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt || true

# ---- Runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Create a non-root user (UID 10001, no shell, no home write access)
RUN groupadd --system --gid 10001 pbirs \
 && useradd --system --uid 10001 --gid pbirs \
        --no-create-home --shell /usr/sbin/nologin pbirs

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=pbirs:pbirs pbirs_export/  ./pbirs_export/
COPY --chown=pbirs:pbirs pbi_import/    ./pbi_import/
COPY --chown=pbirs:pbirs migrate.py     ./
COPY --chown=pbirs:pbirs pyproject.toml ./
COPY --chown=pbirs:pbirs README.md      ./
COPY --chown=pbirs:pbirs CHANGELOG.md   ./

# Writable artifacts dir owned by the non-root user
RUN mkdir -p /artifacts && chown -R pbirs:pbirs /artifacts
VOLUME ["/artifacts"]

USER pbirs

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import migrate" || exit 1

# Default to --help; users override with --assess / --full / etc.
ENTRYPOINT ["python", "migrate.py"]
CMD ["--help"]
