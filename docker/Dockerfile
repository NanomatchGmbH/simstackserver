FROM ghcr.io/prefix-dev/pixi:latest

RUN useradd -m -s /bin/bash simstack

WORKDIR /app

# Copy manifest and lockfile first so dependency layer is cached separately from source
COPY pyproject.toml pixi.lock ./
COPY SimStackServer/ ./SimStackServer/

RUN chown -R simstack:simstack /app

USER simstack

# Install the locked environment (default feature only — no dev/test/lint extras)
RUN pixi install --manifest-path pyproject.toml

# Switch back to root so the entrypoint can fix bind-mount ownership before
# dropping privileges via gosu
USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Bind to all interfaces inside the container; Docker networking provides isolation
ENV SIMSTACK_BIND_HOST=0.0.0.0

# Mount points (declared for documentation; actual mounts are in docker-compose.yml):
#   /home/simstack/  — entire home directory; contains workspace, certs, server config

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
