"""LoRA fine-tuning of Qwen3.8-27B on its own successful SwapBench trajectories (rejection-sampling FT).

  modal run rft/train_lora.py::smoke                # load, LoRA, one fwd/bwd step
  modal run rft/train_lora.py::train --data sft.jsonl [--max-examples N --epochs 1]
  modal run rft/train_lora.py::merge               # merged bf16 model on the volume

Data (from build_sft.py): one example per customer turn, {"prompt": [messages up to the customer's
turn], "completion": [assistant/tool messages until the next customer turn], "tools": [...]}.
Rendered with the model's own chat template; loss on assistant tokens only (reasoning included), so
training matches what the model sees at inference. One example per sequence: no packing (on Gated
DeltaNet layers, packing silently mixes sequences without seq_idx-aware kernels).

Volume and app names come from SWAPBENCH_HF_CACHE_VOLUME (default hf-cache), SWAPBENCH_RFT_VOLUME (default
swapbench-rft) and SWAPBENCH_RFT_APP (default swapbench-rft); the Modal environment from MODAL_ENVIRONMENT.
The merged model lands in the hf-cache volume at /root/.cache/huggingface/swapbench/qwen27b-rft, which
serve_vllm.py mounts at the same path (serve it with MODEL=<that path>).
"""
import json
import os

import modal

BASE = "Qwen/Qwen3.8-27B"
OUT = "/root/.cache/huggingface/swapbench"
image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu24.04", add_python="3.12")
    .apt_install("git", "build-essential")
    .uv_pip_install("torch==2.11.0", index_url="https://download.pytorch.org/whl/cu128")
    .uv_pip_install("transformers>=5.8.0", "peft>=0.18", "accelerate>=1.10", "datasets", "huggingface_hub[hf_transfer]",
                    "flash-linear-attention", "tilelang", "ninja", "packaging", "wheel")  # tilelang: fla refuses Triton <3.7.1 backward on Hopper
    # transformers only takes the fast Gated DeltaNet path (fla + causal-conv1d); without it the torch
    # fallback runs out of memory at 8k tokens on an H200. No prebuilt wheel for this torch: build with gcc.
    .run_commands("CC=gcc CXX=g++ MAX_JOBS=16 CAUSAL_CONV1D_FORCE_BUILD=TRUE pip install --no-build-isolation causal-conv1d")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "TOKENIZERS_PARALLELISM": "false"})
)
hf_cache = modal.Volume.from_name(os.environ.get("SWAPBENCH_HF_CACHE_VOLUME", "hf-cache"), create_if_missing=True)
data_vol = modal.Volume.from_name(os.environ.get("SWAPBENCH_RFT_VOLUME", "swapbench-rft"), create_if_missing=True)
app = modal.App(os.environ.get("SWAPBENCH_RFT_APP", "swapbench-rft"))
VOLS = {"/root/.cache/huggingface": hf_cache, "/data": data_vol}


def load_model():
    import torch
    from transformers import AutoModelForImageTextToText, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForImageTextToText.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cuda")
    return tok, model


def add_lora(model, r=32):
    from peft import LoraConfig, get_peft_model
    cfg = LoraConfig(r=r, lora_alpha=2 * r, lora_dropout=0.0, task_type="CAUSAL_LM",
                     # attention and MLP projections of the language model only (not the vision tower)
                     target_modules=r"model\.language_model\..*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)")
    model = get_peft_model(model, cfg)
    model.print_trainable_parameters()
    return model


def _ids(tok, msgs, tools, gen):
    out = tok.apply_chat_template(msgs, tools=tools, add_generation_prompt=gen, tokenize=True, return_dict=False)
    if isinstance(out, dict) or hasattr(out, "keys"):  # transformers v5 may still hand back a BatchEncoding
        out = out["input_ids"]
    return list(out)


def encode(tok, ex, max_len, why=None):
    """Token ids + labels (-100 outside assistant tokens) for one example; None if too long or inconsistent."""
    tools = ex.get("tools")
    msgs = list(ex["prompt"])
    prev = _ids(tok, msgs, tools, True)
    ids, labels = list(prev), [-100] * len(prev)
    for m in ex["completion"]:
        msgs.append(m)
        nxt_gen = m["role"] == "tool"  # after a tool result, the model speaks again
        cur = _ids(tok, msgs, tools, nxt_gen)
        if cur[:len(prev)] != prev:
            if why is not None:
                why["not_prefix_stable"] = why.get("not_prefix_stable", 0) + 1
            return None  # template not prefix-stable here; skip rather than mislabel
        new = cur[len(prev):]
        ids += new
        labels += new if m["role"] == "assistant" else [-100] * len(new)
        prev = cur
    if len(ids) > max_len:
        if why is not None:
            why["too_long"] = why.get("too_long", 0) + 1
        return None
    return ids, labels


@app.function(image=image, volumes=VOLS, timeout=1800, cpu=8)
def check_data(n: int = 50):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(BASE)
    exs = [json.loads(l) for l in open("/data/sft.jsonl")][:n]
    why, ok, lens, trained = {}, 0, [], []
    for x in exs:
        e = encode(tok, x, 20000, why)
        if e:
            ok += 1
            lens.append(len(e[0]))
            trained.append(sum(l != -100 for l in e[1]))
    print(json.dumps({"checked": len(exs), "ok": ok, "skipped": why, "mean_tokens": sum(lens) / max(ok, 1),
                      "max_tokens": max(lens or [0]), "mean_trained_tokens": sum(trained) / max(ok, 1)}))
    if ok:  # show what the model is trained on, once
        e = encode(tok, exs[0], 20000)
        print(tok.decode([t for t, l in zip(*e) if l != -100])[:1500])


@app.local_entrypoint()
def check(n: int = 50):
    check_data.remote(n=n)


@app.function(image=image, gpu="H200", volumes=VOLS, timeout=3600)
def smoke():
    import time

    import torch
    tok, model = load_model()
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = add_lora(model)
    model.train()  # gradient checkpointing only applies in training mode
    print(json.dumps({"mem_after_load_gb": round(torch.cuda.memory_allocated() / 1e9, 1)}))
    ids = torch.randint(100, 20000, (1, 8192), device="cuda")
    t0 = time.time()
    out = model(input_ids=ids, labels=ids)
    out.loss.backward()
    torch.cuda.synchronize()
    print(json.dumps({"loss": float(out.loss), "fwd_bwd_s_8k": round(time.time() - t0, 1),
                      "max_mem_gb": round(torch.cuda.max_memory_allocated() / 1e9, 1)}))


@app.function(image=image, gpu="H200", volumes=VOLS, timeout=6 * 3600)
def train_remote(max_examples: int = 0, epochs: int = 1, lr: float = 1e-4, max_len: int = 20000, r: int = 32):
    import random
    import time

    import torch
    tok, model = load_model()
    model.gradient_checkpointing_enable()
    model.enable_input_require_grads()
    model = add_lora(model, r)
    exs = [json.loads(l) for l in open("/data/sft.jsonl")]
    random.Random(0).shuffle(exs)
    if max_examples:
        exs = exs[:max_examples]
    enc = [e for e in (encode(tok, x, max_len) for x in exs) if e]
    print(f"encoded {len(enc)} of {len(exs)} examples; tokens {sum(len(i) for i, _ in enc)}; "
          f"trained tokens {sum(sum(l != -100 for l in lab) for _, lab in enc)}")
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.0)
    steps = epochs * len(enc)
    accum = 16
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 20) * max(0.0, 1 - s / max(steps / accum, 1)))
    model.train()
    t0, n, tot = time.time(), 0, 0.0
    for ep in range(epochs):
        random.Random(ep).shuffle(enc)
        for i, (ids, lab) in enumerate(enc):
            x = torch.tensor([ids], device="cuda")
            y = torch.tensor([lab], device="cuda")
            loss = model(input_ids=x, labels=y).loss / accum
            loss.backward()
            tot += float(loss) * accum
            n += 1
            if n % accum == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
            if n % 50 == 0:
                print(json.dumps({"step": n, "of": steps, "loss": round(tot / 50, 4), "elapsed_s": round(time.time() - t0)}),
                      flush=True)
                tot = 0.0
    os.makedirs(f"{OUT}/qwen27b-rft-adapter", exist_ok=True)
    model.save_pretrained(f"{OUT}/qwen27b-rft-adapter")
    hf_cache.commit()
    print("saved adapter")


@app.function(image=image, gpu="H200", volumes=VOLS, timeout=3600, memory=262144)
def merge_remote():
    import shutil

    from huggingface_hub import snapshot_download
    from peft import PeftModel
    tok, model = load_model()
    model = PeftModel.from_pretrained(model, f"{OUT}/qwen27b-rft-adapter").merge_and_unload()
    dst = f"{OUT}/qwen27b-rft"
    model.save_pretrained(dst, safe_serialization=True)
    src = snapshot_download(BASE)
    for f in os.listdir(src):  # tokenizer, chat template, processor and generation configs from the base
        if not f.endswith(".safetensors") and not f.endswith(".index.json") and f != "config.json":
            p = os.path.join(src, f)
            if os.path.isfile(p):
                shutil.copy(p, dst)
    hf_cache.commit()
    print("merged to", dst, os.listdir(dst)[:20])


@app.local_entrypoint()
def train(data: str = "", max_examples: int = 0, epochs: int = 1, lr: float = 1e-4):
    if data:
        with data_vol.batch_upload(force=True) as b:
            b.put_file(data, "/sft.jsonl")
    train_remote.remote(max_examples=max_examples, epochs=epochs, lr=lr)


@app.local_entrypoint()
def merge():
    merge_remote.remote()
