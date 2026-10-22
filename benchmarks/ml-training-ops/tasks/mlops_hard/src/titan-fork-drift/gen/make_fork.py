"""Turn a clean torchtitan v0.2.2 checkout into "our internal fork": intentional changes plus,
optionally, injected faults.

    python make_fork.py <torchtitan_dir> --faults rope,loss,clip     # the broken fork (task start)
    python make_fork.py <torchtitan_dir> --faults ""                 # the fork as it should be

Intentional changes (must survive any fix; several make "copy upstream back" produce a different
loss curve):
  max_norm default 0.5; a cosine_floor LR decay; c4_test shuffled with a fixed seed; smaller output
  init; a chunked cross-entropy (memory); a TITAN_RUN_TAG banner; TITAN_ROPE_THETA override plumbing.
  An explicit attention softmax scale attribute; contiguous dataset shards for small datasets.
Faults:
  attn  - attention softmax scale computed from the model dim instead of the head dim
  loss  - chunked cross-entropy silently drops the tail chunk
  shard - every data-parallel rank reads shard 0 (all ranks train on the same data)
"""
import argparse
import os


def sub(root, rel, old, new, count=1):
    p = os.path.join(root, rel)
    s = open(p).read()
    assert s.count(old) >= 1, (rel, old[:70])
    open(p, "w").write(s.replace(old, new, count))


def apply(root, faults):
    # ---- intentional changes
    sub(root, "torchtitan/config/job_config.py", "    max_norm: float | int = 1.0",
        "    max_norm: float | int = 0.5  # tighter clipping after the March loss spikes (INC-2291)")
    sub(root, "torchtitan/components/lr_scheduler.py",
        '''            elif lr_decay_type == "cosine":
                curr_adjustment = 0.5 * (1.0 + math.cos(math.pi * progress))''',
        '''            elif lr_decay_type == "cosine":
                curr_adjustment = 0.5 * (1.0 + math.cos(math.pi * progress))
            elif lr_decay_type == "cosine_floor":  # cosine that never goes below 10% (long runs)
                curr_adjustment = max(0.1, 0.5 * (1.0 + math.cos(math.pi * progress)))''')
    sub(root, "torchtitan/hf_datasets/text_datasets.py",
        '''        loader=lambda path: load_dataset(path, split="train"),''',
        '''        # shuffled once with a fixed seed: the raw shard is sorted by crawl date
        loader=lambda path: load_dataset(path, split="train").shuffle(seed=1234),''')
    sub(root, "torchtitan/models/llama3/model/model.py",
        "        final_out_std = self.model_args.dim**-0.5",
        "        final_out_std = 0.5 * self.model_args.dim**-0.5  # smaller output init (see infra-notes/init.md)")
    sub(root, "torchtitan/train.py", "def main(trainer_class: type[Trainer]) -> None:",
        '''def main(trainer_class: type[Trainer]) -> None:
    if os.environ.get("TITAN_RUN_TAG"):
        logger.info(f"run tag: {os.environ['TITAN_RUN_TAG']}")''')
    s = open(os.path.join(root, "torchtitan/train.py")).read()
    if "\nimport os\n" not in s:
        sub(root, "torchtitan/train.py", "import ", "import os\nimport ", 1)
    rope_old = "    freqs = 1.0 / (theta ** (torch.arange(0, dim, 2)[: (dim // 2)].float() / dim))"
    rope_denom = "dim"
    sub(root, "torchtitan/models/llama3/model/model.py", rope_old,
        f'''    theta = float(os.environ.get("TITAN_ROPE_THETA", theta))  # per-run override for long-context sweeps
    half = torch.arange(0, dim, 2)[: (dim // 2)].float()
    freqs = 1.0 / (theta ** (half / {rope_denom}))''')
    s = open(os.path.join(root, "torchtitan/models/llama3/model/model.py")).read()
    if "\nimport os\n" not in s:
        sub(root, "torchtitan/models/llama3/model/model.py", "import math", "import math\nimport os")
    tail = "n - CE_CHUNK + 1" if "loss" in faults else "n"
    sub(root, "torchtitan/components/loss.py",
        '''def cross_entropy_loss(pred: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    """Cross-entropy loss with sum reduction for token-based normalization."""
    return torch.nn.functional.cross_entropy(
        pred.flatten(0, 1).float(),
        labels.flatten(0, 1),
        reduction="sum",
        ignore_index=IGNORE_INDEX,
    )''',
        f'''CE_CHUNK = 3000  # tokens per chunk


def cross_entropy_loss(pred: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    """Cross-entropy loss with sum reduction for token-based normalization.

    Computed in chunks so the fp32 copy of the logits never exists for the whole batch at once
    (saves several GB at long sequence lengths on 128k-vocab models).
    """
    logits = pred.flatten(0, 1)
    flat = labels.flatten(0, 1)
    n = logits.shape[0]
    total = logits.new_zeros((), dtype=torch.float32)
    for i in range(0, {tail}, CE_CHUNK):
        total = total + torch.nn.functional.cross_entropy(
            logits[i : i + CE_CHUNK].float(),
            flat[i : i + CE_CHUNK],
            reduction="sum",
            ignore_index=IGNORE_INDEX,
        )
    return total''')
    attn_scale = "model_args.dim**-0.5" if "attn" in faults else "self.head_dim**-0.5"
    sub(root, "torchtitan/models/llama3/model/model.py",
        "        self.head_dim = model_args.dim // model_args.n_heads\n",
        "        self.head_dim = model_args.dim // model_args.n_heads\n"
        f"        # explicit softmax temperature (same as the SDPA default); kept as an attribute so the\n"
        f"        # attention-temperature sweeps can override it per layer\n"
        f"        self.attn_scale = {attn_scale}\n")
    sub(root, "torchtitan/models/llama3/model/model.py",
        """                        xv,  # (bs, n_kv_heads, seqlen, head_dim)
                        enable_gqa=self.enable_gqa,
                    )
                    .transpose(1, 2)
                    .contiguous()
                )  # (bs, seqlen, n_local_heads, head_dim)
            case _:""",
        """                        xv,  # (bs, n_kv_heads, seqlen, head_dim)
                        enable_gqa=self.enable_gqa,
                        scale=self.attn_scale,
                    )
                    .transpose(1, 2)
                    .contiguous()
                )  # (bs, seqlen, n_local_heads, head_dim)
            case _:""")
    shard_index = "0" if "shard" in faults else "dp_rank"
    sub(root, "torchtitan/hf_datasets/text_datasets.py",
        "        self._data = split_dataset_by_node(ds, dp_rank, dp_world_size)",
        f"""        if isinstance(ds, Dataset) and dp_world_size > 1:
            # small map-style datasets: contiguous shards keep each document's neighbours on one rank
            self._data = ds.shard(num_shards=dp_world_size, index={shard_index}, contiguous=True)
        else:
            self._data = split_dataset_by_node(ds, dp_rank, dp_world_size)""")
    if False:
        sub(root, "torchtitan/distributed/utils.py",
            '''        # Will reach here if any non-PP parallelism is used.
        # If only using PP, total_norm will be a local tensor.
        total_norm = total_norm.full_tensor()''',
            '''        # Will reach here if any non-PP parallelism is used.
        # If only using PP, total_norm will be a local tensor.
        # Perf: skip the extra all-reduce; shard norms are within a few % of the global norm
        # for FSDP-sharded weights, which is plenty for clipping.
        total_norm = total_norm.to_local()''')


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--faults", default="attn,loss,shard")
    a = ap.parse_args()
    apply(a.root, {f for f in a.faults.split(",") if f})
    print("fork written to", a.root, "faults:", a.faults or "none")
