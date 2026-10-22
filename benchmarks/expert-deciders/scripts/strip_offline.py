"""Strip the offline expert-deciders files to public rows (ids, labels, scores; no conversation text or explanations).

  python scripts/strip_offline.py <ed-dir> results/runs/offline <rename.json>

<ed-dir> (private archive) holds steps.jsonl, labels.jsonl and scores/scores_<arm>.jsonl from scripts/ed_build_steps.py,
ed_experts.py and ed_arms.py. Raw run directory names inside step ids are mapped to neutral provider labels.
"""
import glob
import json
import os
import sys

# Original raw directory names (which name the providers) -> neutral names, from a private JSON file
# {"prov_hidden/<original dir>": "prov_hidden/<label>_<model>", ...}; the mapping is not in this repository.
# ed_build_steps.py AGENTS uses the neutral names.
RENAME = {}


def fix(s):
    for a, b in RENAME.items():
        s = s.replace(a, b)
    return s


def main(ed, out):
    os.makedirs(os.path.join(out, "scores"), exist_ok=True)
    keep = ("id", "agent", "run", "split", "scenario", "point", "tool", "violations", "bad", "heldout")
    with open(os.path.join(out, "steps.jsonl"), "w") as f:
        for s in map(json.loads, open(os.path.join(ed, "steps.jsonl"))):
            f.write(fix(json.dumps({k: s[k] for k in keep})) + "\n")
    with open(os.path.join(out, "labels.jsonl"), "w") as f:
        for x in map(json.loads, open(os.path.join(ed, "labels.jsonl"))):
            f.write(fix(json.dumps({k: x.get(k) for k in ("expert", "id", "go_ahead", "flipped", "in_tok", "out_tok")})) + "\n")
    for p in sorted(glob.glob(os.path.join(ed, "scores", "scores_*.jsonl"))):
        with open(os.path.join(out, "scores", os.path.basename(p)), "w") as f:
            for x in map(json.loads, open(p)):
                f.write(fix(json.dumps({k: x[k] for k in ("id", "p", "in_tok", "out_tok", "latency") if k in x})) + "\n")


if __name__ == "__main__":
    RENAME.update(json.load(open(sys.argv[3])) if len(sys.argv) > 3 else {})
    main(*sys.argv[1:3])
