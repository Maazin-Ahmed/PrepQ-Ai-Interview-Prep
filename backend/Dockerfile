# ──────────────────────────────────────────
# Stage 1: Build — install C-extension deps
# ──────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# build-essential is only needed to compile native extensions (e.g. cryptography,
# aiohttp). We install wheels into a prefix here and copy only those into the
# final image, keeping the runner lean.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ──────────────────────────────────────────
# Stage 2: Minimal production runner
# ──────────────────────────────────────────
FROM python:3.12-slim AS runner

WORKDIR /app

# Copy only the installed packages from the builder — no compiler toolchain
COPY --from=builder /install /usr/local

# Copy source code
COPY . .

# Non-root user for security
RUN adduser --disabled-password --gecos "" prepq \
 && chown -R prepq:prepq /app
USER prepq

EXPOSE 8000

# --workers 2 = sensible default for a small container; tune via env if needed
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
