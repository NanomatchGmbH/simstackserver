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

# Bind to all interfaces inside the container; Docker networking provides isolation
ENV SIMSTACK_BIND_HOST=0.0.0.0

# Mount points (declared for documentation; actual mounts are in docker-compose.yml):
#   /home/simstack/.config/SimStackServer  — server_config.yml
#   /home/simstack/simstack_workspace      — workflow data (must match resources.basepath)

EXPOSE 8000

# -D = foreground mode (no daemonisation)
ENTRYPOINT ["pixi", "run", "--manifest-path", "/app/pyproject.toml", "serve"]
