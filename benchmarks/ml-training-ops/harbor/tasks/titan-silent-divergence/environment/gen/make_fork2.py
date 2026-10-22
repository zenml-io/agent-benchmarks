"""Fork v2 for the slow-divergence task: the intentional fork changes of make_fork.py (no code faults),
plus an internal ~200M flavor, a sharded local `corpus` dataset with `training.exclude_shards`,
and a 1000-step training config.

    python make_fork2.py <torchtitan_dir>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_fork import apply, sub  # noqa: E402

CONFIG = '''[job]
dump_folder = "./outputs"
description = "internal 200M reference run"

[metrics]
log_freq = 1
disable_color_printing = true

[model]
name = "llama3"
flavor = "internal200m"
hf_assets_path = "./tests/assets/tokenizer"

[optimizer]
name = "AdamW"
lr = 6e-4
eps = 1e-8

[lr_scheduler]
warmup_steps = 50
decay_ratio = 0.8
decay_type = "cosine_floor"
min_lr_factor = 0.0

[training]
local_batch_size = 4
seq_len = 1024
max_norm = 0.5
steps = 1000
dataset = "corpus"
dataset_path = "/data/corpus"
exclude_shards = []

[parallelism]
data_parallel_shard_degree = -1

[checkpoint]
enable = false

[activation_checkpoint]
mode = "none"

[debug]
seed = 42
deterministic = true
'''


def apply2(root):
    apply(root, set())
    sub(root, "torchtitan/models/llama3/__init__.py", '''    "8B": TransformerModelArgs(''', '''    "internal200m": TransformerModelArgs(
        dim=1024, n_layers=16, n_heads=16, vocab_size=2048, rope_theta=500000
    ),
    "8B": TransformerModelArgs(''')
    sub(root, "torchtitan/config/job_config.py", '''    dataset_path: str | None = None
    """''', '''    exclude_shards: list[str] = field(default_factory=list)
    """Shard file names to skip in sharded local datasets (e.g. "part-0007.jsonl")."""

    dataset_path: str | None = None
    """''', 1)
    s = open(os.path.join(root, "torchtitan/config/job_config.py")).read()
    if "from dataclasses import" in s and "field" not in s.split("from dataclasses import")[1].split("\n")[0]:
        sub(root, "torchtitan/config/job_config.py", "from dataclasses import ", "from dataclasses import field, ")
    sub(root, "torchtitan/hf_datasets/text_datasets.py", '''    "c4_test": DatasetConfig(''', '''    # internal corpus: one jsonl file per shard, read in file order
    "corpus": DatasetConfig(
        path="/data/corpus",
        loader=lambda path: _load_corpus(path),
        sample_processor=_process_c4_text,
    ),
    "c4_test": DatasetConfig(''')
    sub(root, "torchtitan/hf_datasets/text_datasets.py", '''def _process_c4_text(''', '''_EXCLUDE: list[str] = []


def _load_corpus(path: str):
    import glob
    files = sorted(f for f in glob.glob(os.path.join(path, "*.jsonl")) if os.path.basename(f) not in _EXCLUDE)
    return load_dataset("json", data_files=files, split="train")


def _process_c4_text(''')
    sub(root, "torchtitan/hf_datasets/text_datasets.py", '''    dataset_name = job_config.training.dataset''', '''    _EXCLUDE[:] = list(job_config.training.exclude_shards)
    dataset_name = job_config.training.dataset''')
    s = open(os.path.join(root, "torchtitan/hf_datasets/text_datasets.py")).read()
    if "\nimport os\n" not in s:
        sub(root, "torchtitan/hf_datasets/text_datasets.py", "from functools import partial", "import os\nfrom functools import partial")
    open(os.path.join(root, "torchtitan/models/llama3/train_configs/internal_200m.toml"), "w").write(CONFIG)


if __name__ == "__main__":
    apply2(sys.argv[1])
    print("fork v2 written to", sys.argv[1])
