"""64 shards of payment events (jsonl). ~3% of events are delivered twice (same id, same content),
possibly in different shards. Deterministic."""
import json
import os
import random

rng = random.Random(4242)
os.makedirs("data/shards", exist_ok=True)
USERS = [f"u{i:04d}" for i in range(400)]
events = []
for i in range(64 * 2500):
    u = rng.choice(USERS)
    events.append({"id": f"ev-{i:07d}", "user": rng.choice([u, u.upper(), " " + u + " "]),
                   "amount": rng.randint(1, 50_000), "currency": rng.choice(["USD", "USD", "EUR", "GBP", "JPY"]),
                   "status": rng.choice(["settled"] * 8 + ["pending", "reversed"])})
dups = rng.sample(events, len(events) * 3 // 100)
stream = events + dups
rng.shuffle(stream)
for s in range(64):
    with open(f"data/shards/part-{s:03d}.jsonl", "w") as f:
        for e in stream[s::64]:
            f.write(json.dumps(e) + "\n")
