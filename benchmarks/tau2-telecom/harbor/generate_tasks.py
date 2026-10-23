"""Build the 40 Harbor tasks (tau2 Telecom test split) from Harbor's tau3-bench adapter.

    python harbor/generate_tasks.py                       # clones the two pinned sources into a temp dir
    python harbor/generate_tasks.py --tau2-root /path/to/tau2-bench --adapter-root /path/to/harbor/adapters/tau3-bench

Standard library only. Steps:

1. Fetch tau2-bench at TAU2_REF (sparse: source, data, pyproject, README) and Harbor's
   `adapters/tau3-bench` at HARBOR_REF, unless local checkouts are given.
2. Run the adapter (`Tau3BenchAdapter`, telecom domain) for the 40 ids of tau2's Telecom `test`
   split, in tau2's loader order (`tasks.json` order), which is the order the original run numbered. The adapter writes one Harbor task per id from its own template:
   an MCP sidecar (`tau3-runtime`) that serves tau2's agent tools and the simulated user, and a
   verifier that grades with tau2's `evaluate_simulation`.
3. Patch every task so it matches the original run and is safe to grade (each patch asserts the
   text it replaces, so a changed adapter fails loudly instead of producing a silently different task):
   - both images install tau2-bench at TAU2_REF instead of the repository's moving default branch, and the
     agent's image drops tau2's Telecom task files (they list every task's expected actions);
   - the simulated user is pinned to gpt-4.1-2025-04-14 with provider-default settings (the adapter
     defaults to GPT-5.2 with reasoning effort "low"); it always calls OpenAI directly;
   - tau2's limits are the original run's: 100 steps, 10 tool errors (the adapter's runtime uses 200);
   - the agent gets 1200 s (the original episode timeout), the sandbox 2 CPUs and 4 GB;
   - the grader passes the communicate scorer that tau2 requires since 2026-10-19 (substring, as in the
     original run); the adapter's grader omits it and fails on every attempt against this tau2 commit;
   - the grader gets no API key (Telecom has no natural-language assertions, so it never calls a model);
   - test.sh deletes stale rewards first and always writes a reward;
   - the oracle is rebuilt as `solution/build_state.py` (the adapter's oracle logic plus check modes),
     with one alternative valid solution and up to three shortcuts per task for the four checks.
4. Rename each task to `telecom-test-NN` (NN = the original run's case number: the index in tau2's
   loader order, checked against the original run's recorded cases).

Outputs `harbor/tasks/` (replaced) and `harbor/tasks/index.json` (case -> tau2 task id -> Harbor hub id).
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAU2_REPO = "https://github.com/sierra-research/tau2-bench"
TAU2_REF = "05736c27219b769d0be507574dd3135010916644"  # the commit the original run used
HARBOR_REPO = "https://github.com/harbor-framework/harbor"
HARBOR_REF = "209a48a7424218828465c3c716b042f2b381dbed"  # main on 2026-10-22
USER_MODEL = "gpt-4.1-2025-04-14"
MAX_STEPS = 100
MAX_ERRORS = 10
AGENT_TIMEOUT_SEC = 1200.0
TAU2_SPARSE = ["/*", "!/web/", "!/tests/", "!/docs/", "!/figs/", "!/examples/", "!/data/voice/", "!/data/tau2/results/"]
TEMPLATES = HERE / "task_files"
ORIGINAL_CASES = HERE.parent / "results" / "runs" / "replay" / "baseline.jsonl"
HIDDEN_FROM_AGENT = ["data/tau2/domains/telecom/tasks*.json", "data/tau2/domains/telecom/split_tasks.json"]


def run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def fetch(repo: str, ref: str, dest: Path, sparse: list[str]) -> Path:
    dest.mkdir(parents=True)
    run(["git", "init", "-q"], dest)
    run(["git", "remote", "add", "origin", repo], dest)
    run(["git", "sparse-checkout", "set", "--no-cone", *sparse], dest)
    run(["git", "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", ref], dest)
    run(["git", "checkout", "-q", "FETCH_HEAD"], dest)
    return dest


def replace_once(text: str, old: str, new: str, where: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{where}: expected exactly one {old!r}; the adapter template changed")
    return text.replace(old, new)


def pinned_install(dockerfile: str, where: str) -> str:
    """Swap the adapter's moving `git clone --depth=1` for a sparse fetch of TAU2_REF."""
    old = 'git clone --depth=1 "${TAU2_BENCH_REPO}" "${TAU2_BENCH_ROOT}"'
    sparse = " ".join(f"'{p}'" for p in TAU2_SPARSE)
    new = (
        'mkdir -p "${TAU2_BENCH_ROOT}" && cd "${TAU2_BENCH_ROOT}" && git init -q '
        '&& git remote add origin "${TAU2_BENCH_REPO}" '
        f"&& git sparse-checkout set --no-cone {sparse} "
        '&& git fetch -q --depth 1 --filter=blob:none origin "${TAU2_BENCH_REF}" '
        "&& git checkout -q FETCH_HEAD && rm -rf .git && cd /app"
    )
    text = replace_once(dockerfile, old, new, where)
    return replace_once(text, 'ARG TAU2_BENCH_REPO="https://github.com/sierra-research/tau2-bench.git"\n',
                        'ARG TAU2_BENCH_REPO="https://github.com/sierra-research/tau2-bench.git"\n'
                        f"ARG TAU2_BENCH_REF={TAU2_REF}\n", where)


def patch_compose(text: str, where: str) -> str:
    old_env = (
        "    environment:\n"
        "      - OPENAI_API_KEY=${OPENAI_API_KEY:-}\n"
        "      - OPENAI_BASE_URL=${OPENAI_BASE_URL:-}\n"
        "      - TAU2_USER_MODEL=${TAU2_USER_MODEL:-gpt-5.2}\n"
        "      - TAU2_USER_REASONING_EFFORT=${TAU2_USER_REASONING_EFFORT:-low}\n"
    )
    # An empty TAU2_USER_REASONING_EFFORT makes the runtime send no reasoning setting (gpt-4.1 has none),
    # matching the original run's UserSimulator(llm=..., llm_args=None).
    new_env = (
        "    environment:\n"
        "      - OPENAI_API_KEY=${OPENAI_API_KEY:-}\n"
        f"      - TAU2_USER_MODEL={USER_MODEL}\n"
        "      - TAU2_USER_REASONING_EFFORT=\n"
    )
    return replace_once(text, old_env, new_env, where)


def patch_task_toml(text: str, where: str, case: int, source_id: str, hub_id: str) -> str:
    text = replace_once(text, f'name = "sierra-research/tau3-bench__{hub_id}"',
                        f'name = "zenml/tau2-telecom-test-{case:02d}"', where)
    text = replace_once(text, 'keywords = ["tau3-bench", "telecom", "tool-use"]',
                        'keywords = ["tau2-bench", "telecom", "tool-use", "simulated-user"]', where)
    text = replace_once(text, 'category = "customer_service"\n',
                        'category = "customer_service"\n'
                        f"source_task_id = {json.dumps(source_id)}\n"
                        f'source_split = "test"\ncase = {case}\n'
                        f'tau2_bench_ref = "{TAU2_REF}"\nadapter = "harbor adapters/tau3-bench @ {HARBOR_REF}"\n'
                        f'user_model = "{USER_MODEL}"\n', where)
    text = replace_once(
        text,
        'env = { OPENAI_API_KEY = "${OPENAI_API_KEY}", OPENAI_BASE_URL = "${OPENAI_BASE_URL}", '
        'TAU2_NL_ASSERTIONS_MODEL = "${TAU2_NL_ASSERTIONS_MODEL:-gpt-5.2}" }\n',
        "", where)
    text = replace_once(text, "timeout_sec = 3600.0", f"timeout_sec = {AGENT_TIMEOUT_SEC}", where)
    text = replace_once(text, "build_timeout_sec = 600.0", "build_timeout_sec = 900.0", where)
    text = replace_once(text, "cpus = 4\nmemory_mb = 8192", "cpus = 2\nmemory_mb = 4096", where)
    # The main container needs no model settings: agents bring their own, the user simulator runs in the sidecar.
    return re.sub(r'\nenv = \{ OPENAI_API_KEY = "\$\{OPENAI_API_KEY\}".*TAU2_USER_LLM_ARGS_JSON:-\}" \}\n', "\n", text,
                  count=1)


def patch_evaluate(text: str, where: str) -> str:
    """Pass the communicate scorer tau2 requires since 2026-10-19, set as in the original run.

    Without it every grade fails with a TypeError and scores 0. Substring matching is what the
    original run used, and it keeps the grader free of model calls.
    """
    text = replace_once(
        text,
        '    get_now = _import_attr("tau2.utils.utils", "get_now")\n',
        '    get_now = _import_attr("tau2.utils.utils", "get_now")\n'
        '    CommunicateScoring = _import_attr("tau2.data_model.semantic_communication", "CommunicateScoring")\n'
        '    CommunicateScorer = _import_attr("tau2.data_model.semantic_communication", "CommunicateScorer")\n',
        where)
    return replace_once(
        text,
        "        env_kwargs=env_kwargs,\n    )\n",
        "        env_kwargs=env_kwargs,\n"
        "        communicate_scoring=CommunicateScoring(scorer=CommunicateScorer.SUBSTRING),\n    )\n",
        where)


def patch_task(task_dir: Path, case: int, source_id: str, hub_id: str) -> None:
    where = task_dir.name
    env = task_dir / "environment"
    for dockerfile in (env / "Dockerfile", env / "runtime-server" / "Dockerfile"):
        dockerfile.write_text(pinned_install(dockerfile.read_text(), f"{where}/{dockerfile.relative_to(task_dir)}"))
    # The agent's container keeps tau2 (the verifier runs there) but not the Telecom task definitions,
    # which hold every task's expected actions. The sidecar keeps them; it serves only the MCP tools.
    main = env / "Dockerfile"
    main.write_text(replace_once(main.read_text(), "&& rm -rf .git && cd /app",
                                 f"&& rm -rf .git {' '.join(HIDDEN_FROM_AGENT)} && cd /app", f"{where}/Dockerfile"))
    compose = env / "docker-compose.yaml"
    compose.write_text(patch_compose(compose.read_text(), f"{where}/docker-compose.yaml"))

    toml = task_dir / "task.toml"
    text = patch_task_toml(toml.read_text(), f"{where}/task.toml", case, source_id, hub_id)
    if "TAU2_USER_MODEL" in text or "OPENAI_API_KEY" in text:
        raise SystemExit(f"{where}/task.toml: model settings left in task.toml")
    toml.write_text(text)

    for config_path in (env / "runtime-server" / "task_config.json", task_dir / "tests" / "config.json"):
        config = json.loads(config_path.read_text())
        config["max_steps"], config["max_errors"] = MAX_STEPS, MAX_ERRORS
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=True))

    evaluate = task_dir / "tests" / "evaluate.py"
    evaluate.write_text(patch_evaluate(evaluate.read_text(), f"{where}/tests/evaluate.py"))
    shutil.copy(TEMPLATES / "test.sh", task_dir / "tests" / "test.sh")
    (task_dir / "tests" / "test.sh").chmod(0o755)

    # Rebuild the oracle around one data file and one script (same reference logic as the adapter's).
    solve = (task_dir / "solution" / "solve.sh").read_text()
    oracle = json.loads(solve.split("<<'JSON'\n", 1)[1].split("\nJSON\n", 1)[0])
    oracle |= {"domain": "telecom", "task_id": source_id}
    solution = task_dir / "solution"
    (solution / "oracle.json").write_text(json.dumps(oracle, indent=2, ensure_ascii=True))
    shutil.copy(TEMPLATES / "build_state.py", solution / "build_state.py")
    for name, mode, folder in (("solve.sh", "reference", solution),
                               ("rechecks.sh", "rechecks", solution / "alternatives")):
        folder.mkdir(exist_ok=True)
        (folder / name).write_text(f"#!/bin/bash\npython3 /solution/build_state.py {mode}\n")
        (folder / name).chmod(0o755)
    shortcuts = task_dir / "tests" / "shortcuts"
    shortcuts.mkdir()
    for mode in shortcut_modes(oracle["actions"]):
        (shortcuts / f"{mode}.sh").write_text(f"#!/bin/bash\npython3 /solution/build_state.py {mode}\n")
        (shortcuts / f"{mode}.sh").chmod(0o755)


def shortcut_modes(actions: list[dict]) -> list[str]:
    """Shortcuts whose actions differ from the reference's, so each must score 0."""
    names = [a["name"] for a in actions]
    user = [a for a in actions if a.get("requestor") == "user"]
    agent = [a for a in actions if a.get("requestor") != "user"]
    modes = ["do_nothing"]
    if names != ["transfer_to_human_agents"]:
        modes.append("transfer_now")
    if user and agent:
        modes.append("account_side_only")
    return modes


def test_split_ids(tau2_root: Path) -> list[str]:
    """The test split's task ids in tau2's loader order: `tasks.json` order, filtered by `split_tasks.json`.

    `split_tasks.json` lists the same ids in a different order; numbering by it would give no task its
    original case number.
    """
    telecom = tau2_root / "data/tau2/domains/telecom"
    test = {str(i) for i in json.loads((telecom / "split_tasks.json").read_text())["test"]}
    tasks = json.loads((telecom / "tasks.json").read_text())
    ids = [str(t["id"]) for t in (tasks["tasks"] if isinstance(tasks, dict) else tasks) if str(t["id"]) in test]
    if len(ids) != 40 or set(ids) != test:
        raise SystemExit(f"expected the 40 test ids in tasks.json, found {len(ids)}")
    return ids


def check_against_original_run(test_ids: list[str]) -> None:
    """Fail unless case N is the task the original run recorded as case N (results/runs/replay/baseline.jsonl)."""
    recorded = {}
    for line in ORIGINAL_CASES.read_text().splitlines():
        row = json.loads(line)
        recorded[row["case"]] = row["tau2"]["task_id"]
    wrong = [case for case, task_id in recorded.items() if test_ids[case] != task_id]
    if len(recorded) != len(test_ids) or wrong:
        raise SystemExit(f"case numbers differ from the original run for cases {wrong or 'missing'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tau2-root", type=Path)
    ap.add_argument("--adapter-root", type=Path, help="harbor/adapters/tau3-bench checkout")
    ap.add_argument("--out", type=Path, default=HERE / "tasks")
    a = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="tau2-telecom-gen-") as tmp_s:
        tmp = Path(tmp_s)
        tau2_root = a.tau2_root or fetch(TAU2_REPO, TAU2_REF, tmp / "tau2-bench", TAU2_SPARSE)
        adapter_root = a.adapter_root or fetch(HARBOR_REPO, HARBOR_REF, tmp / "harbor",
                                               ["/adapters/tau3-bench/"]) / "adapters" / "tau3-bench"
        test_ids = test_split_ids(tau2_root)
        check_against_original_run(test_ids)

        sys.path.insert(0, str(adapter_root / "src"))
        from tau3_bench.adapter import Tau3BenchAdapter

        raw = tmp / "raw"
        adapter = Tau3BenchAdapter(raw, overwrite=True, task_ids=test_ids, domains=["telecom"], tau2_root=tau2_root)
        adapter.run()
        hub_ids = {t.source_id: t.local_task_id for t in adapter._load_tau_tasks() if t.source_id in set(test_ids)}

        if a.out.exists():
            shutil.rmtree(a.out)
        a.out.mkdir(parents=True)
        index = []
        for case, source_id in enumerate(test_ids):
            hub_id = hub_ids[source_id]
            task_dir = a.out / f"telecom-test-{case:02d}"
            shutil.copytree(raw / hub_id, task_dir)
            patch_task(task_dir, case, source_id, hub_id)
            index.append({"case": case, "task": task_dir.name, "tau2_task_id": source_id, "harbor_hub_task": hub_id})
        (a.out / "index.json").write_text(json.dumps(
            {"tau2_bench_ref": TAU2_REF, "harbor_adapter_ref": HARBOR_REF, "split": "test", "tasks": index}, indent=2))
    print(f"wrote {len(index)} tasks to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
