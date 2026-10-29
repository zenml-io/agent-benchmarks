# The Codex arm's base image: Node, the Codex CLI at a pinned version, and uv. Built by harbor/round_task/build_images.sh.
# Harbor's codex agent finds `codex` on PATH and skips its own install, which would need the network.
FROM node:22-bookworm-slim
ARG CODEX_VERSION=0.160.1
ARG UV_VERSION=0.13.4
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl git procps ripgrep \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g "@openai/codex@${CODEX_VERSION}" && codex --version
RUN curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | env UV_INSTALL_DIR=/usr/local/bin sh && uv --version
