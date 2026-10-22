set -e
# build the fork: clean torchtitan v0.2.2 + our changes + the faults; no git history
git clone -q --depth 1 --branch v0.2.2 https://github.com/pytorch/torchtitan /app/titan
python "${GEN_DIR:-/tmp/gen}/make_fork.py" /app/titan --faults attn,loss,shard
rm -rf /app/titan/.git /app/titan/.github
cd /app/titan && pip install --no-cache-dir -r /tmp/titan-requirements.txt && pip install --no-cache-dir --no-deps -e .
