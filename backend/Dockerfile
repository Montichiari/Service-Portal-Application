# syntax=docker/dockerfile:1

# Backend container image (T-DO-1; DO-1, DO-3, DO-4).
#
# Two stages. The builder resolves and installs the dependency tree into a
# virtualenv; the runtime stage copies that virtualenv and the application
# source, and carries no pip cache, no build metadata and no toolchain. Both
# stages sit on the same base tag so the interpreter the venv was built
# against is byte-identical to the one that runs it.
#
# 3.14-slim matches the interpreter this project is developed against
# (Python 3.14.5), deliberately rather than by default: a container running a
# different minor version than the developer's machine is a difference that
# only ever surfaces in production.

ARG PYTHON_VERSION=3.14-slim

# --- builder -----------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Its own virtualenv rather than the base image's site-packages, so the
# runtime stage copies one self-contained directory instead of reaching into
# /usr/local and picking up whatever else lives there.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dependencies ahead of source: this layer is keyed on requirements.txt alone,
# so an edit to a route file does not reinstall the tree.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# --- runtime -----------------------------------------------------------------
FROM python:${PYTHON_VERSION} AS runtime

# DO-4. The sink is stdout/stderr and nothing else: no log file is configured
# here or in the app, and `docker diff` on a container that has served traffic
# shows an empty filesystem delta, which is the check that proves it rather
# than the absence of a FileHandler in the source.
#
# PYTHONUNBUFFERED is belt-and-braces, and deliberately not claimed as more
# than that — it was measured, not assumed. uvicorn logs through a
# `logging.StreamHandler`, which flushes on every record, so its access lines
# and the XC-14 traceback reach the pipe promptly with or without this set
# (verified by running the image with it unset: identical, prompt output). It
# stays because it covers what does *not* go through logging — a bare
# `print()`, a library writing to stdout directly, a C-level write — where the
# 8 KiB block buffer on a non-tty stdout is real and a container killed
# mid-buffer loses the contents. Don't upgrade this comment back into a claim
# that uvicorn needs it.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root, with a fixed uid/gid so a bind-mounted volume's ownership is
# predictable and so the value is the same on every build. --no-create-home
# because nothing writes to a home directory; the app owns no writable path
# inside the container at all.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# Source, owned by root and readable by `app`: the process can read its own
# code but cannot rewrite it.
COPY app ./app
# Alembic ships in the image on purpose. DO-21 runs migrations as a pipeline
# step against RDS, and the natural way to do that is this same image with a
# different command — the alternative, a second image built from the same
# source, is a second thing that can drift from the code it migrates.
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

USER app

EXPOSE 8000

# No HEALTHCHECK. /health is a *readiness* probe (DO-22) — answering 503 when
# the database is unreachable is the whole point of it — and Docker/ECS treat
# a failing HEALTHCHECK as liveness: they would kill and restart the task. A
# database blip would then become a restart storm on top of the outage,
# instead of the ALB target group quietly pulling the task from rotation and
# putting it back when the database returns. The ALB check (DO-5) is where
# /health belongs. If a container-level check is ever wanted here, it must not
# touch the database.

# No .env file is copied and none is expected. app/config.py names `.env` as a
# source, and pydantic-settings simply skips a missing one, so every setting
# resolves from the process environment: DATABASE_URL and JWT_SECRET_KEY are
# required and the container will refuse to start without them (DO-3), which
# is the correct failure — a misconfigured task that dies at launch beats one
# that serves traffic signing tokens with a default.

# exec form, so uvicorn is pid 1 and receives SIGTERM directly — ECS sends it
# on every deploy, and a shell-form CMD would swallow it and force the 30s
# kill. --host 0.0.0.0 because the ALB reaches the task across the container's
# network namespace. No --reload and no --workers: one process per task, with
# ECS doing the scaling.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
