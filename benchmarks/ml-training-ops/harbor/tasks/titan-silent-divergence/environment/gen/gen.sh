set -e
git clone -q --depth 1 --branch v0.2.2 https://github.com/pytorch/torchtitan /app/titan
python "${GEN_DIR:-/tmp/gen}/make_fork2.py" /app/titan
python "${GEN_DIR:-/tmp/gen}/make_corpus.py" /app/titan/tests/assets/c4_test/data.json /data/corpus
rm -rf /app/titan/.git /app/titan/.github
cd /app/titan && pip install --no-cache-dir -r /tmp/titan-requirements.txt && pip install --no-cache-dir --no-deps -e .
chmod -R a-w /data/corpus
