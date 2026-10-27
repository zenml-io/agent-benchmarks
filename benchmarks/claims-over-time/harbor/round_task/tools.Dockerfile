# Adds what both improver arms share to an arm's base image: the claims agent's Python environment (the benchmark's
# locked `agent` extra, Python 3.12) and the precedent library, plus, with RERUN_TOOL=1 (the Codex arm only), the
# `claims-rerun` command. Built twice by build_images.sh, once on the Codex base and once on the pro arm's base image.
# The round's own files (the agent version, the appeals, the tools' code) are added per round by the task's
# environment/Dockerfile.
ARG BASE=missing
FROM ${BASE}
ARG AGENT_USER=root
ARG PRECEDENTS_SHA256=unknown
ARG RERUN_TOOL=0
USER root
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
COPY requirements.txt /tmp/claims-requirements.txt
RUN uv venv --python 3.12 /opt/claims-venv \
    && uv pip install --python /opt/claims-venv/bin/python --no-cache -r /tmp/claims-requirements.txt \
    && chmod -R a+rX /opt/uv-python /opt/claims-venv
COPY precedents.jsonl /claims/data/precedents.jsonl
RUN if [ "${RERUN_TOOL}" = 1 ]; then \
      printf '#!/bin/sh\nexec /opt/claims-venv/bin/python /claims/bin/rerun.py "$@"\n' > /usr/local/bin/claims-rerun \
      && chmod 755 /usr/local/bin/claims-rerun; fi \
    && chown -R "${AGENT_USER}:" /claims
LABEL claims.precedents_sha256=${PRECEDENTS_SHA256}
USER ${AGENT_USER}
