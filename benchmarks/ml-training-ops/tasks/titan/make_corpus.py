"""Split torchtitan's c4_test sample into 20 jsonl shards under <out>; shard part-0016 is scraper junk
(log spam) that slipped past the quality filter."""
import json
import os
import random
import sys

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
docs = [json.loads(l) for l in open(src)]
rng = random.Random(7)
SPAM = ["ERROR 502 upstream connect error or disconnect/reset before headers. retried and the latest reset reason: connection termination",
        "WARN  rate limit exceeded for key ****, backing off 30s",
        "INFO  GET /static/js/main.4f2a9c.js 200 0.004s"]
for s in range(20):
    with open(os.path.join(out, f"part-{s:04d}.jsonl"), "w") as f:
        for d in docs[s * 100:(s + 1) * 100]:
            if s == 16:
                d = {"text": "\n".join(rng.choice(SPAM) for _ in range(rng.randint(60, 140)))}
            f.write(json.dumps({"text": d["text"]}) + "\n")
print("wrote 20 shards to", out)
