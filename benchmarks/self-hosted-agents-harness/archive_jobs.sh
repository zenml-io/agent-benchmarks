#!/usr/bin/env bash
# Archive each finished run's raw data to a private Modal volume ($MODAL_RAW_VOLUME in
# environment $MODAL_ENVIRONMENT). jobs/ is gitignored and only exists on the machine running
# the experiment; this keeps trajectories, Harbor logs and vLLM metrics.
# Run it from the benchmark directory (the one holding attempts.jsonl and jobs/).
#   ./archive_jobs.sh          # once
#   ./archive_jobs.sh --loop   # every 20 min (run detached with setsid nohup)
# A run counts as finished once its record is in attempts.jsonl; uploaded runs are
# listed in jobs/.archived so each is uploaded once.
export PATH="$HOME/.local/bin:$PATH"
cd "${BENCH_DIR:-.}"
VOL="${MODAL_RAW_VOLUME:?set MODAL_RAW_VOLUME to the private volume for raw runs}"
ENV="${MODAL_ENVIRONMENT:-main}"

archive_once() {
  touch jobs/.archived
  python3 -c "import json; [print(json.loads(l)['job_name']) for l in open('attempts.jsonl') if l.strip()]" |
  while read -r job; do
    grep -qxF "$job" jobs/.archived && continue
    ok=1
    [ -d "jobs/$job" ] && { modal volume put -e $ENV -f $VOL "jobs/$job" "/jobs/$job" >/dev/null 2>&1 || ok=0; }
    for f in "jobs/$job.log" "jobs/$job.metrics.jsonl"; do
      [ -f "$f" ] && { modal volume put -e $ENV -f $VOL "$f" "/$f" >/dev/null 2>&1 || ok=0; }
    done
    if [ $ok = 1 ]; then echo "$job" >> jobs/.archived; echo "$(date +%H:%M) archived $job"; \
    else echo "$(date +%H:%M) FAILED $job (retry next pass)"; fi
  done
  modal volume put -e $ENV -f $VOL attempts.jsonl /attempts.jsonl >/dev/null 2>&1
}

archive_once
if [ "${1:-}" = "--loop" ]; then
  while true; do sleep 1200; archive_once; done
fi
