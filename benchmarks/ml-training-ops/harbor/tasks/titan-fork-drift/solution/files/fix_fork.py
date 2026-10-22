"""Reference fix: undo the three injected faults, keep every intentional change."""
import os

T = "/app/titan"
FIXES = [
    ("torchtitan/models/llama3/model/model.py", "self.attn_scale = model_args.dim**-0.5", "self.attn_scale = self.head_dim**-0.5"),
    ("torchtitan/components/loss.py", "for i in range(0, n - CE_CHUNK + 1, CE_CHUNK):", "for i in range(0, n, CE_CHUNK):"),
    ("torchtitan/hf_datasets/text_datasets.py", "index=0, contiguous=True", "index=dp_rank, contiguous=True"),
]
for rel, old, new in FIXES:
    p = os.path.join(T, rel)
    s = open(p).read()
    assert old in s, (rel, old)
    open(p, "w").write(s.replace(old, new))
print("fixed")
