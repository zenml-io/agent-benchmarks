"""
Train the HICRIC appeal-outcome classifier (DistilBERT) on Modal, score it on HICRIC's own test split,
and predict the claims-over-time cases with it.

    uv run --extra modal modal run harness/hicric/hicric_modal.py::train     # ~$1-3 on one H100
    uv run --extra modal modal run harness/hicric/hicric_modal.py::predict   # cents; needs inputs.jsonl
    uv run --extra modal modal run harness/hicric/hicric_modal.py::predict --control

`train` fine-tunes with HICRIC's own code (github.com/TPAFS/hicric at HICRIC_COMMIT) and its
`distilbert.yaml` settings on the published Persius/imr-appeals train split, keeps the model in a
Modal Volume, and writes $CLAIMS_WORK_DIR/hicric/reproduction.json and test_probabilities.jsonl.
`predict` reads $CLAIMS_WORK_DIR/hicric/inputs.jsonl (from `hicric_ref.py inputs`) and writes
probabilities.jsonl. Both run as ephemeral apps, so Modal stops them when the call returns.

Needs MODAL_ENVIRONMENT and a logged-in Modal CLI. Volume and app names come from
MODAL_HICRIC_VOLUME and MODAL_APP_PREFIX (defaults below).
"""

import json
import os
import time
from pathlib import Path

import modal

HICRIC_COMMIT = "37d88ab02833862c3f0b0ad4d0b3d52a96a705b2"
DATASET = "Persius/imr-appeals"
DATASET_REVISION = "c68b70e0faf74cd2b5731ea02ad7ba7d99a11b8b"
CONFIG = "src/modeling/config/outcome_prediction/distilbert.yaml"
GPU, GPU_PER_HOUR = "H100!", 3.95  # Modal list price, Oct 2026
MODEL_DIR = "/vol/distilbert"

HERE = Path(__file__).resolve().parent
WORK = Path(os.environ.get("CLAIMS_WORK_DIR") or HERE.parent.parent / "work") / "hicric"

# HICRIC's training module imports its scraping helpers and ONNX export at import time, so the image
# carries those packages too. Versions follow HICRIC's requirements.txt where they still resolve together.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install("numpy==1.26.4", "torch==2.6.0", "transformers==4.51.3", "accelerate==1.6.0",
                 "huggingface_hub==0.30.2", "datasets==3.5.0", "scikit-learn==1.5.0", "scipy==1.13.1",
                 "safetensors", "pyyaml", "wandb==0.18.1", "onnx==1.17.0", "onnxruntime==1.17.3",
                 "html2text==2020.1.16", "pdfplumber==0.10.3", "polars==0.20.5", "beautifulsoup4==4.12.3",
                 "requests==2.32.3", "pyarrow==19.0.1")
    .run_commands(f"git clone https://github.com/TPAFS/hicric.git /hicric && cd /hicric && git checkout {HICRIC_COMMIT}")
)
volume = modal.Volume.from_name(os.environ.get("MODAL_HICRIC_VOLUME", "hicric-model"), create_if_missing=True)
app = modal.App(f"{os.environ.get('MODAL_APP_PREFIX', 'agent')}-claims-hicric", image=image)


def _hicric() -> None:
    import sys

    os.chdir("/hicric")
    sys.path.insert(0, "/hicric")


def _plain(o: object) -> object:
    return o.tolist() if hasattr(o, "tolist") else str(o)


def _probabilities(model, tokenizer, texts: list[str], batch_size: int = 64) -> list[list[float]]:
    """Softmax over HICRIC's three classes, with jurisdiction and insurance type 'Unspecified' as in training."""
    import torch

    model.to("cuda").eval()
    out = []
    for i in range(0, len(texts), batch_size):
        enc = tokenizer(texts[i:i + batch_size], truncation=True, padding=True, return_tensors="pt").to("cuda")
        n = enc["input_ids"].shape[0]
        unspecified = torch.full((n,), 2, dtype=torch.long, device="cuda")
        with torch.no_grad():
            logits = model(**enc, jurisdiction_id=unspecified, insurance_type_id=unspecified)["logits"]
        out += torch.softmax(logits.float(), dim=-1).cpu().tolist()
    return out


@app.function(gpu=GPU, volumes={"/vol": volume}, timeout=3 * 3600)
def train_remote(limit: int = 0, epochs: float = 0) -> str:
    """Fine-tune with HICRIC's helpers and config, save the best model, and score it on the test split.

    `limit` and `epochs` shrink the run for a smoke test; 0 keeps HICRIC's full data and epoch count.
    """
    from functools import partial

    import numpy as np
    import torch
    from datasets import load_dataset
    from transformers import AutoTokenizer, TrainingArguments

    t0 = time.time()
    _hicric()
    from src.modeling.eval_hf_outcome_predictor import (
        compute_metrics,
        compute_metrics_w_threshold,
    )
    from src.modeling.train_outcome_predictor import (
        ID2LABEL,
        INSURANCE_TYPE_MAP,
        JURISDICTION_MAP,
        LABEL2ID,
        CPUEvalTrainer,
        DataCollatorWithMetadata,
        add_integral_ids_batch,
        compute_metrics2,
        construct_label,
        create_metadata_model,
        load_and_split,
    )
    from src.modeling.util import load_config

    cfg = load_config(CONFIG)
    data = load_dataset(DATASET, revision=DATASET_REVISION)
    if limit:
        data["train"], data["test"] = data["train"].shuffle(seed=0).select(range(limit)), data["test"].select(range(limit // 4))
    data["train"].to_json("/tmp/train.jsonl")
    # HICRIC's own split: 20% of the published train split becomes the per-epoch eval set that picks
    # the best checkpoint; the published test split is only touched after training.
    dataset = load_and_split("/tmp/train.jsonl")
    tokenizer = AutoTokenizer.from_pretrained(cfg["pretrained_hf_model_key"], model_max_length=512, truncation=True)
    # HICRIC pads every 1,000-row map batch to its longest row; padding per training batch instead gives
    # the same model outputs (attention masks hide padding) at a fraction of the compute.
    dataset = dataset.map(lambda ex: tokenizer(ex["text"], truncation=True), batched=True)
    dataset = dataset.map(partial(add_integral_ids_batch, label2id=LABEL2ID, jurisdiction_map=JURISDICTION_MAP,
                                  insurance_type_map=INSURANCE_TYPE_MAP), batched=True)
    model = create_metadata_model(pretrained_model_key=cfg["pretrained_hf_model_key"], base_model_name=cfg["base_model_name"],
                                  num_labels=3, id2label=ID2LABEL, label2id=LABEL2ID)
    args = TrainingArguments(
        output_dir="/tmp/checkpoints", learning_rate=cfg["learning_rate"], per_device_train_batch_size=cfg["batch_size"],
        per_device_eval_batch_size=cfg["batch_size"], eval_accumulation_steps=16, num_train_epochs=epochs or cfg["num_epochs"],
        weight_decay=cfg["weight_decay"], fp16=cfg["dtype"] == "float16", eval_strategy="epoch", save_strategy="epoch",
        save_total_limit=1, load_best_model_at_end=True, torch_compile=False, report_to="none",
        dataloader_num_workers=4, dataloader_pin_memory=True)
    trainer = CPUEvalTrainer(model=model, args=args, train_dataset=dataset["train"], eval_dataset=dataset["test"],
                             processing_class=tokenizer, data_collator=DataCollatorWithMetadata(tokenizer=tokenizer),
                             compute_metrics=compute_metrics2)
    t1 = time.time()
    trainer.train()
    t2 = time.time()
    model_dir = f"{MODEL_DIR}-smoke" if limit else MODEL_DIR
    trainer.save_model(model_dir)
    tokenizer.save_pretrained(model_dir)
    volume.commit()

    test = data["test"].to_list()
    probs = _probabilities(trainer.model, tokenizer, [r["text"] for r in test])
    labels = np.array([construct_label(r["decision"], r["sufficiency_id"], LABEL2ID) for r in test])
    logits = torch.log(torch.tensor(probs))
    try:
        metrics = {"test_argmax": compute_metrics(logits, labels),
                   "test_threshold": compute_metrics_w_threshold(logits.numpy(), labels, cfg["eval_threshold"])}
    except Exception as e:  # noqa: BLE001
        # A metric failure must not lose a finished training run; hicric_ref.py rescores from the rows.
        metrics = {"metric_error": repr(e)}
    report = {
        "hicric_commit": HICRIC_COMMIT, "dataset_revision": DATASET_REVISION, "config": cfg,
        "best_checkpoint": trainer.state.best_model_checkpoint, "n_train": len(dataset["train"]),
        "n_selection": len(dataset["test"]), "n_test": len(test),
        **metrics, "limit": limit, "epochs": epochs or cfg["num_epochs"],
        "log_history": trainer.state.log_history,
        "seconds": {"setup": t1 - t0, "train": t2 - t1, "total_in_container": time.time() - t0},
        "gpu": torch.cuda.get_device_name(0),
    }
    rows = [{"i": i, "decision": r["decision"], "sufficiency_id": r["sufficiency_id"],
             "probabilities": dict(zip(ID2LABEL.values(), p))} for i, (r, p) in enumerate(zip(test, probs))]
    # JSON text, because the metrics hold numpy scalars and the local side has no numpy to unpickle them.
    out = json.dumps({"report": report, "rows": rows}, default=_plain)
    with open(f"{model_dir}/reproduction.json", "w") as f:
        f.write(out)
    volume.commit()
    return out


@app.function(gpu=GPU, volumes={"/vol": volume}, timeout=1800)
def predict_remote(items: list[dict]) -> list[dict]:
    """Three-class probabilities for each {id, text} item from the saved model."""
    from transformers import AutoTokenizer

    _hicric()
    from src.modeling.train_outcome_predictor import (
        ID2LABEL,
        LABEL2ID,
        create_metadata_model,
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = create_metadata_model(pretrained_model_key=MODEL_DIR, base_model_name="distilbert", num_labels=3,
                                  id2label=ID2LABEL, label2id=LABEL2ID)
    probs = _probabilities(model, tokenizer, [x["text"] for x in items])
    return [{"id": x["id"], "probabilities": dict(zip(ID2LABEL.values(), p))} for x, p in zip(items, probs)]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _cost(seconds: float) -> dict:
    return {"wall_seconds": round(seconds, 1), "gpu": GPU, "usd_per_hour": GPU_PER_HOUR,
            "usd": round(seconds / 3600 * GPU_PER_HOUR, 2)}


@app.local_entrypoint()
def train(limit: int = 0, epochs: float = 0) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    t = time.time()
    out = json.loads(train_remote.remote(limit, epochs))
    if limit:
        print(json.dumps({k: v for k, v in out["report"].items() if k != "log_history"}, indent=1, default=str)[:3000])
        print(f"smoke run: {_cost(time.time() - t)}; nothing written")
        return
    out["report"]["cost_from_local_wall_clock"] = _cost(time.time() - t)
    (WORK / "reproduction.json").write_text(json.dumps(out["report"], indent=1, default=str))
    _write_jsonl(WORK / "test_probabilities.jsonl", out["rows"])
    r = out["report"]
    print(json.dumps({k: r.get(k) for k in ("test_argmax", "test_threshold", "metric_error", "seconds",
                                            "cost_from_local_wall_clock")}, indent=1, default=str))


@app.local_entrypoint()
def predict(control: bool = False) -> None:
    """Predict inputs.jsonl into probabilities.jsonl, or with --control the HICRIC test first-span inputs."""
    src, dest = ("control_inputs", "control_probabilities") if control else ("inputs", "probabilities")
    with open(WORK / f"{src}.jsonl") as f:
        items = [json.loads(x) for x in f if x.strip()]
    t = time.time()
    rows = predict_remote.remote([{"id": x["id"], "text": x["text"]} for x in items])
    by = {x["id"]: x for x in items}
    _write_jsonl(WORK / f"{dest}.jsonl", [r | {"input": by[r["id"]]["input"]} for r in rows])
    print(json.dumps({"n": len(rows), "cost": _cost(time.time() - t)}))
