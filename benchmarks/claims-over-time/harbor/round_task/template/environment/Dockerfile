# Filled in by scripts/round.py. The base image comes from harbor/round_task/build_images.sh; the build context holds
# this round's files: the current agent version, the appeals (truth on revealed rows only), the round settings, the
# tools' code and, for the Codex arm, the recorded runs.
FROM ${base_image}
USER root
COPY claims/ /claims/
RUN mkdir -p /claims/reruns && chown -R ${user}: /claims/agent /claims/data/cases.jsonl /claims/reruns /claims/round.json \
    && if [ -d /claims/runs ]; then chown -R ${user}: /claims/runs; fi
# Pro arm: a read-only copy of the registered current version at its registered working directory, so the Kitaru
# worker in the trial runs the same version the workspace lists.
RUN if [ -n "${mirror_dir}" ]; then mkdir -p "${mirror_dir}" && cp -r /claims/registered/claims_agent "${mirror_dir}/" \
    && chmod -R a+rX,go-w "${mirror_dir}"; fi
USER ${user}
WORKDIR /claims
