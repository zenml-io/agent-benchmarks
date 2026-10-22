# ml-training-ops on Harbor

The 24 ml-training-ops tasks as Harbor-native tasks: the same instructions, code, data and reference fixes the original runs used (built from `../tasks/` unchanged), graded in a fresh container that gets only the agent's `/app` back, with plausible wrong fixes that must score 0, a different valid solution that must score 1 (21 of the 22 CPU tasks), job configs for every setup of the original runs, `dataset.toml` and a repo-root `registry.json` entry.

Status: **native**. The 22 CPU tasks passed the four checks on Modal on 2026-10-22 (results below). The two torchtitan tasks need 2 GPUs per trial; only their GPU-free checks ran. No model agent has been run through this version yet.

## What is in this folder

| Path | What it is |
|---|---|
| `build.py` | Builds `tasks/` from `../tasks/mlops_tasks/` (v1) and `../tasks/mlops_hard/src/` (hard, v2, v3, torchtitan; through that folder's `build.py`), adding `shared/` and `overlays/<task>/`. Rebuild after changing any of them (a unit test fails if `tasks/` is stale), then refresh the digests: `harbor add tasks/<task> -t dataset.toml` (or `-t dataset-titan/dataset.toml`). |
| `tasks/` | The 24 built tasks (3.6 MB), committed so `harbor run --repo` works without a build step. |
| `shared/` | `test.sh`, `junit_ok.py`, `pytest.ini` (every task's grader entrypoint), `shortcuts/forge_grade.sh` (every task), `stepcount/` (grader instrumentation, three tasks), `titan-requirements.txt` (pinned torchtitan dependencies). |
| `overlays/<task>/` | Per task: `shortcuts/*.sh` (become `tests/shortcuts/`), `alternatives/*.sh` (become `solution/alternatives/`), and for eight tasks `tests/` files that replace the original grader (see "Grader changes"). |
| `setups/` | Job configs: `modal.yaml`, task lists (`tasks-*.yaml`) and one file per setup (`setup-*.yaml`). Conditions differ only in their setup file. |
| `dataset.toml`, `dataset-titan/dataset.toml` | Harbor dataset manifests: `zenml/ml-training-ops` (22 CPU tasks) and `zenml/ml-training-ops-titan` (2 GPU tasks), with task digests. |
| `scripts/verify_tasks.py` | The four checks through Harbor on Modal (`--titan-static` for the torchtitan tasks' GPU-free part). |
| `scripts/check_local.py` | The same variants graded locally without containers (CPU tasks; needs the task images' Python packages). |
| `scripts/summarize.py` | Solve rate per setup and task from job folders, infrastructure errors apart, paired difference against a baseline. |
| `tests/test_harbor_tasks.py` | Fast offline tests: `test.sh` against forged and short-circuited runs, `junit_ok.py`, every task loads in Harbor's own `TaskConfig`, nothing the grader knows is in the image, `tasks/` matches a fresh build, the answer-file graders on every variant. |

## How a task works

- The agent's container is built from `environment/Dockerfile` (the original: `python:3.11-slim`, CPU torch 2.5.1, numpy 2.1.3, pytest 8.4.1, pyyaml 6.0.2; ray 2.50.1 or git where a task needs them; generated inputs are made at image build by the task's `gen/` script, which is then deleted). `instruction.md` is the original instruction.
- The verifier runs in a **separate container** from the same image (`[verifier] environment_mode = "separate"`). Harbor copies the agent's `/app` out after the agent finishes (`artifacts = ["/app"]`) and back into the fresh container, then uploads `tests/` and runs `tests/test.sh`. Nothing the agent did outside `/app` (installed packages, a patched pytest or torch, files in `/tests` or `/logs/verifier`, background processes) reaches the grader. Every task's work product lives in `/app`, so a legitimate solution grades the same as in the original shared container.
- `tests/test.sh` deletes any `reward.txt` / `reward.json`, writes 0 first, runs `python -P -m pytest /tests/test_outputs.py` with the grader's own `pytest.ini`, no conftest files, no plugin autoload and a JUnit report at a random path, and writes 1 only if pytest exits 0 and `junit_ok.py` finds at least one test, all passed (a process that exits 0 early, or a skipped test, scores 0). `-P` keeps `/app` off `sys.path`, so an agent's `pytest.py` cannot replace the test runner.
- The hidden tests are the original ones (re-run the job, with fault injection, hidden seeds, world sizes or cluster histories, against reference code and answer keys in `tests/`), except where a shortcut passed them (next section).
- `solution/solve.sh` is the original reference fix. `solution/alternatives/*.sh` and `tests/shortcuts/*.sh` are scripts Harbor's oracle agent runs in place of it for the checks; the reference files stay at `/solution/files` for scripts that build on them.

## Grader changes from the original runs

Writing a shortcut per task found eight graders that a plausible wrong fix passed. Those tests now also check the missing requirement; everything else grades as before. A trial of the original runs may have passed through one of these holes (the trajectories are in the private archive, not published), so for these tasks the published solve rates are an upper bound under the new graders.

| Task | Shortcut that passed the original grader | Added check |
|---|---|---|
| `nan-loss` | rescale the output layer's init back down after the wide `mul_(100.0)` (the source check only looked for that text) | `build_model()` must produce the original initialization (seeds 0 and 1) |
| `resume-checkpoint` | ignore `--resume` and retrain from step 0 (deterministic, so the final weights match) | a resume from step 150 to 300 runs at most 150 optimizer steps (counted by patching `Adam.step`) |
| `atomic-checkpoint` | atomic writes, but every restart retrains from step 0 | the final restart, with checkpoints present, runs fewer optimizer steps than the whole job (`shared/stepcount`) |
| `exact-resume` | every restart retrains from step 0 | as above |
| `elastic-churn` | (a) every launch retrains from step 0; (b) rank 0 runs the single-process `reference.py` and the other ranks only wait | (a) a launch that finishes with checkpoints present runs fewer steps than the whole job; (b) in a 3-rank launch every rank runs at least one backward pass per training step |
| `uneven-shard-hang` | give every rank `floor(n / world)` examples (the collectives pair up, up to world-1 examples are skipped each epoch), which the instruction forbids | every training example reaches the model at least once per epoch (row hashes logged by a forward pre-hook, `overlays/uneven-shard-hang/tests/rowlog`) |
| `regression-bisect` | name the right commit, then make `train.py` report a higher accuracy | the grader evaluates the saved weights itself with the repository's own data, model and test-time normalisation (`tests/eval_pristine.py`) instead of reading `train.py`'s report |
| `ray-exactly-once` | compute `out/totals.json` in the driver and never feed the live `totals` actor (it can then never overcount) | once the job is done, the live `totals` actor must hold the exact totals |

`scripts/check_local.py --original` grades a variant with the original test: it shows each of these shortcuts scoring 1 there (results below) and 0 under the new grader. The instrumentation (a `sitecustomize.py` on the job's `PYTHONPATH`, set only for the grader's own launches) records a start line, and the graders fail if it did not load, so it cannot fail open. Judgement calls: `regression-bisect`'s grader uses HEAD's evaluation (global train-set normalisation of the test set); an agent that changes how test accuracy is computed is graded on HEAD's definition. `uneven-shard-hang` counts uses per example over the whole run (at least 3 for 3 epochs), which catches every drop-the-remainder split but would not catch an example used twice in one epoch and never in another.

## The four checks

```bash
cd benchmarks/ml-training-ops
export HARBOR_TELEMETRY=off
python harbor/scripts/verify_tasks.py --cpu-tasks --jobs-dir ~/mlops-harbor-jobs -n 8          # 22 CPU tasks
python harbor/scripts/verify_tasks.py --titan-static --jobs-dir ~/mlops-harbor-jobs -n 2       # torchtitan, GPU-free part
```

It runs three Harbor jobs on Modal (oracle × 5, nop × 1, and every shortcut and alternative once as Harbor's oracle agent on a copy of the task), each in the Modal app `mlops-harbor-checks` so their cost can be read from `modal billing report`, and prints one row per task and check. Shortcuts per task (every task also has `forge_grade.sh`: it writes `reward.json` / `reward.txt` = 1, plants a conftest hook in `/tests` and `/app`, shadows pytest from `/app`, and installs a `.pth` hook that makes `python -m pytest` exit 0):

| Task | Shortcuts (must score 0) | Alternative (must score 1) |
|---|---|---|
| nan-loss | `rescale_init` (above), `nan_to_num` (silence the NaNs) | `logsumexp`: hand-written stable cross-entropy |
| label-shuffle | `no_shuffle` (remove the shuffling) | `index_select`: one permutation via argsort, `index_select` on both tensors |
| resume-checkpoint | `retrain_from_scratch` (above), `model_and_step_only` (no optimizer or schedule state) | `separate_state_file`: training state in a second file, step from the scheduler |
| oom-grad-accum | `smaller_batch` (1024 samples per step, no accumulation) | `accum_mean_4096`: micro-batches of 4096 with size-weighted mean losses |
| ddp-sharding | `sampler_without_set_epoch` (same order every epoch) | `manual_strided_shard`: per-epoch permutation, rank r takes every world-th index |
| eval-mode | `no_grad_only` (no_grad but still in training mode) | `eval_whole_set`: eval mode, one no-grad pass, no restore (the loop calls `train()`) |
| ddp-replica-drift | `average_of_rank_means` (broadcast + DDP-style averaging; wrong for uneven shards) | `normalize_by_global_count`: summed losses, gradients divided by an all-reduced example count |
| uneven-shard-hang | `drop_remainder` (above), `no_gradient_sync` (remove the all-reduce: no hang, ranks diverge) | `zero_grad_padding_steps`: ranks agree on the most batches; a rank out of data joins with zero gradients |
| straggler-diagnosis | `local_rank_as_gpu` (ignores the host's `CUDA_VISIBLE_DEVICES` order), `cordon_everything_suspicious` | `near_start_step`: start step 25 late, numbers as strings |
| corrupt-shard | `any_nonfinite_raw_value` (quarantines junk-column rows, misses derived-feature ones), `feature_columns_only` | `messy_but_right`: full paths, strings, empty lists, unsorted |
| atomic-checkpoint | `retrain_from_scratch` (above), `skip_unloadable` (resume from the newest loadable file; torn files stay visible) | `write_then_link`: `.partial` + fsync + rename, prune after, `save_final` |
| reshard-optimizer | `fresh_moments_on_resize` (restart Adam's moments when the world size changes) | `load_overlapping_ranges`: copy only the source-shard ranges overlapping this rank's slice |
| k8s-unschedulable | `blanket_toleration`, `drop_zone_pin` (placeable today, zone not guaranteed) | `node_affinity_minimal_requests`: required node affinity, minimum requests |
| memory-leak-oom | `plain_floats_only` (fixes one of three leaks), `disable_memo_and_replay` (changes what trains) | `no_memo_trimmed_buffer`: recompute the deterministic augmentation, trimmed copy of the replay buffer |
| exact-resume | `retrain_from_scratch` (above), `scheduler_only` (RNG and data order still diverge) | `replay_data_order`: rebuild the data generator by replaying finished epochs' shuffles |
| k8s-quota-zone | `keep_zone_a_volume` (volume in the wrong zone), `requests_above_quota` | `node_affinity_lean_requests`: node affinity, 80 CPUs / 1000Gi / limit 1400Gi |
| two-stragglers | `only_the_obvious_one` (one of the two incidents) | `reordered_near_steps` |
| regression-bisect | `inflate_reported_accuracy` (above), `more_epochs` (ruled out), `blame_label_smoothing` (the commit that looks guilty) | `scale_lr_in_code_short_sha`: LR scaled with the batch size in `train.py`, 7-character SHA |
| throughput-sla | `float32_no_fsync` (the cheap knobs only; not 10x) | `numpy_features_index_batches`: numpy features, index batches, no mask loop |
| ray-exactly-once | `dedupe_in_memory` (state lost when the totals actor dies), `driver_writes_totals` (above) | none (see "Left") |
| gang-controller | `swallow_api_errors` (no crashes; partial gangs and starvation stay) | `first_fit_shorter_patience`: the reference's structure with first-fit placement and a 20-tick starvation guard (a policy variant, not an independent rewrite) |
| elastic-churn | `retrain_from_scratch`, `rank0_runs_spec` (both above) | `ddp_scaled_loss`: DistributedDataParallel with the loss scaled by world / global batch |
| titan-fork-drift | `revert_clipping_change` (undoes an intentional fork change), `gpu_two_of_three_faults` (GPU test only) | none |
| titan-silent-divergence | `patch_model_code` (neutralises the RoPE override in code instead of the environment), `gpu_delete_bad_shard` (GPU test only) | none |

Results, 2026-10-22 (Harbor 0.24.0, Modal; jobs `m1`-`m3`, 211 trials on the CPU tasks):

| Check | Tasks | Trials | Matched expected |
|---|---|---|---|
| oracle, 5 attempts per task | 22 | 110 | 110 (reward 1) |
| nop | 22 | 22 | 22 (reward 0) |
| `forge_grade.sh` | 22 | 22 | 22 (reward 0) |
| task-specific shortcuts (table above) | 22 | 36 | 36 (reward 0), each for the reason it was written for (read in the test output) |
| alternatives | 21 (none for ray-exactly-once) | 21 | 21 (reward 1) |

No infrastructure errors. A trial took 25-200 s end to end (`ray-exactly-once` and `throughput-sla` about 3 minutes; both sandboxes and grading included), once the task's image was built (the first build of a torch image took 2-4 minutes).

The same variants graded locally without containers (`scripts/check_local.py`, all 20 non-Ray CPU tasks) matched, apart from two local-only effects: on this 4-CPU machine `memory-leak-oom`'s reference fails its own weight comparison (1e-4 after 600 steps) in about a third of runs (differences of 0.018-0.035, from run-to-run float nondeterminism in the 2-thread job), while on Modal it passed 15 of 15 (5 in `m3` plus 10 in `m4-memleak-oracle10`); and killed `elastic-churn` workers survive on a local machine and slow later tests (kill them afterwards; in a sandbox they die with it). With the original hidden tests (`--original`), these shortcuts score 1: `nan-loss/rescale_init`, `resume-checkpoint/retrain_from_scratch`, `atomic-checkpoint/retrain_from_scratch`, `exact-resume/retrain_from_scratch`, `elastic-churn/rank0_runs_spec` and `retrain_from_scratch`, `uneven-shard-hang/drop_remainder`, `regression-bisect/inflate_reported_accuracy` (locally), and `ray-exactly-once/driver_writes_totals` (on Modal, job `orig-ray-driver`); every other shortcut already scored 0 under the original graders.

Grader unit tests (`tests/test_harbor_tasks.py`, 62 tests, about 30 s):

```bash
cd benchmarks/ml-training-ops
uv run --no-project --with pytest --with pyyaml --with numpy --with 'harbor==0.24.0' pytest -q harbor/tests
```

## Running a real comparison

Paid; not run while writing this. Run from `benchmarks/ml-training-ops` with keys in `.env` (names in `.env.example`); every `harbor run` gets `-y`, a new `--job-name` and `-o` outside the checkout. Setups (`harbor/setups/`):

| File | Agent | Original counterpart |
|---|---|---|
| `setup-codex-gpt-6-luna.yaml`, `setup-codex-gpt-6.1-sol.yaml`, `setup-codex-gpt-6-astra.yaml` | Codex CLI pinned to 0.162.1 (the version Harbor installed in the original runs) | vendor-API table, codex rows |
| `setup-terminus2-gpt-6.1-sol.yaml` | Harbor's Terminus 2 (part of Harbor 0.24.0) | terminus-2 / gpt-6.1-sol row |
| `setup-claude-code-haiku-5-5.yaml` | Claude Code pinned to 2.1.296 | the two Claude Code runs (setup failures; see the README) |
| `setup-selfhosted-terminus2.yaml`, `setup-selfhosted-mini-swe-agent.yaml` | the self-hosted harnesses (mini-swe-agent pinned to 2.4.6) against an OpenAI-compatible server | self-hosted table |
| `setup-oracle.yaml`, `setup-nop.yaml` | Harbor's free agents | the checks |

Harbor ignores `-m` when the agent comes from a config file: for another model copy a setup file and change `model_name`, and give each setup its own job. Baseline and condition in the same batch, 5 attempts per task (hard + v2 set, GPT-6 Luna vs GPT-6.1 Sol under Codex):

```bash
cd benchmarks/ml-training-ops && export HARBOR_TELEMETRY=off; D=$(date +%F); \
harbor run -y -c harbor/setups/modal.yaml -c harbor/setups/tasks-hard-v2.yaml -c harbor/setups/setup-codex-gpt-6-luna.yaml -k 5 --env-file .env -o ~/mlops-harbor-jobs --job-name hardv2-codex-luna-$D; \
harbor run -y -c harbor/setups/modal.yaml -c harbor/setups/tasks-hard-v2.yaml -c harbor/setups/setup-codex-gpt-6.1-sol.yaml -k 5 --env-file .env -o ~/mlops-harbor-jobs --job-name hardv2-codex-sol-$D; \
python harbor/scripts/summarize.py ~/mlops-harbor-jobs/hardv2-codex-luna-$D ~/mlops-harbor-jobs/hardv2-codex-sol-$D --baseline "codex / openai/gpt-6-luna" | tee results/harbor-hardv2-codex-$D.md
```

Expected cost and time per setup on the 11 hard + v2 tasks × 5 attempts (55 trials), from the original runs: API about $0.50 (GPT-6 Luna: $0.30 per 33 trials), $5.50 (GPT-6.1 Sol: $3.30 per 33) or $33 (GPT-6 Astra: $19.76 per 33); Modal sandboxes about $0.60 per hour of trial time at 4 CPUs / 8 GB (the checks' bill divided by their trial time), so about $0.05-0.10 per trial of 5-10 minutes and $3-6 per setup; 15-30 minutes at 8 trials at once (the original 33-trial runs took 6-12 minutes; trials take 2-10 minutes each plus grading). The v3 tasks add about $0.02-0.65 of API per task and attempt under Codex; the self-hosted setups add the GPU server (`../self-hosted-agents-harness/`, GPU $1.57-4.29 per hard-set run of 24 trials).

Self-hosted runs keep using the shared harness, which serves the model, runs Harbor and records rows; point it at the Harbor-native tasks with the task lists in `data/`:

```bash
cd benchmarks/ml-training-ops && python ../self-hosted-agents-harness/experiment.py --tasks-file tasks_harbor_hard.json --harnesses terminus-2 -- matrix --configs defaults h200 --concurrency 24 --reps 2 --attempts 3
```

`tasks_harbor_v1.json`, `tasks_harbor_hard.json`, `tasks_harbor_hard2.json` and `tasks_harbor_all.json` list the same tasks as the original `tasks_mlops*.json` with `"path": "harbor/tasks"`; rows get the task-set names `harbor_*`, so they never pool with the published `mlops_*` rows. The original task lists still point at `tasks/`, which is unchanged.

From the registry (after the repository is tagged): `harbor run --repo zenml-io/agent-benchmarks@<tag> -d ml-training-ops@2.0.0 -a <agent> -m <model> -e modal` (or `ml-training-ops-titan@2.0.0`).

## How results map to the original numbers

- Same tasks, instructions, images and reference fixes as the published runs; the self-hosted setups and Codex versions are the original ones. Solve rates on the 14 tasks whose graders did not change are comparable with the README's tables for the same setup and task set (use `summarize.py --infra-as-wrong`: the original counted every trial, harness errors included, as unsolved).
- What will not match, and why:
  - The eight changed graders (above) are stricter. Expect equal or lower solve rates on those tasks: two of the v1 tasks, two of the hard 8 (atomic-checkpoint, uneven-shard-hang), one of the v2 tasks (exact-resume; the v2 runs also included atomic-checkpoint) and three of the v3 tasks.
  - Grading in a separate container adds a second sandbox start (about 5-20 s) per trial and runs timing-sensitive tests (`throughput-sla`) on a machine the agent did not leave busy; a fix that depended on something outside `/app` (none of the reference or alternative fixes do) would now fail.
  - Models behind the same names change; the original vendor-API rounds had 1-3 attempts per task, and the v3 / torchtitan rounds ran one task at a time. Identical self-hosted runs differed by up to 7 solves of 24, so compare per task, paired, with 5 attempts or more.
  - Codex and Claude Code were unpinned in the original runs (0.162.1 and 2.1.296 were installed); the setups pin those versions, which may differ from what a given original trial used if Harbor installed different versions on different days.
  - The torchtitan images now pin torchao 0.18.0 and torchtitan's requirements (`shared/titan-requirements.txt`); the original installed them unpinned at image build.
- Sandbox cost: the self-hosted harness's estimate under-counts these tasks (README, Trust status), and the separate verifier adds sandbox time; read the real cost from `modal billing report` filtered to the job's Modal app.

## The torchtitan tasks

Each trial needs 2x L40S, 8 CPUs and 32 GB, for up to 60 (fork-drift) or 90 (silent-divergence) minutes of agent time plus a 2-6 minute training run in grading, in a second GPU sandbox (separate verifier). Checked without GPUs (`verify_tasks.py --titan-static`: CPU sandboxes, the tests that need no GPU, i.e. `test_intentional_changes_kept` for fork-drift and the corpus / config / code checks for silent-divergence): on 2026-10-22 the pinned images built (torchao 0.18.0 and the rest of `shared/titan-requirements.txt`, read from a cached Modal build of the original unpinned Dockerfile); the reference fix and the untouched fork pass the GPU-free tests; `revert_clipping_change.sh` (fork-drift) and `patch_model_code.sh` (silent-divergence) score 0 on them; `forge_grade.sh` changes no code, so on the GPU-free tests it scores like nop (1), which shows only that the forged reward files were not what decided. Job `t1`, 10 trials.

Needs GPUs, not run here: oracle 5/5 and nop 0 on the training curve, `gpu_two_of_three_faults.sh` and `gpu_delete_bad_shard.sh` = 0, and a different valid fix (none written yet). Command and cost (oracle × 5 + nop + 3 shortcuts per task, 2 × 10 trials, each about 10-20 minutes of two 2-GPU sandboxes; at Modal's L40S price roughly $15-30 in total):

```bash
cd benchmarks/ml-training-ops && HARBOR_TELEMETRY=off python harbor/scripts/verify_tasks.py titan-fork-drift titan-silent-divergence --jobs-dir ~/mlops-harbor-jobs -n 2
```

(`verify_tasks.py` refuses GPU tasks without `--titan-static`; remove `titan-*` from `GPU_TASKS` in the script, or run the three Harbor jobs by hand, to do this on purpose.)

## Spend while building this

All on 2026-10-22, Modal only (no model or judge calls): **$2.52** billed to the checks' Modal app `mlops-harbor-checks` (complete hours 17:00-19:00 UTC: CPU $1.89, memory $0.64, egress $0.001). That covers 234 trials (the four checks on 22 CPU tasks, 211; the torchtitan GPU-free checks, 10, including building both pinned images; 10 extra `memory-leak-oom` oracle runs; one run of a shortcut against the original `ray-exactly-once` grader; a smoke run and a cached-image probe that read the torchtitan package versions), about 4.1 hours of trial time. Image builds may be billed outside the app and are not separable from the workspace bill. Local checks ran on a 4-CPU machine (about 2.5 hours).

## Limits of the port

- Graders that import the agent's code into the test process (five v1 tasks import `/app/data.py` or `train.py`; `throughput-sla` imports `trainer`; `gang-controller` imports `controller.py`) run that code with the grader's privileges: deliberately malicious code could still write a fake JUnit report and exit. The separate container, `-P`, the random report path and the "every test passed" rule stop the forgeries an agent could plant from its own container; running agent code only in subprocesses would close the rest. The other graders run the agent's job as a subprocess.
- Separate grading costs a second sandbox start per trial (a few seconds once the image is cached) and doubles a trial's sandbox count; the torchtitan tasks need a second 2-GPU sandbox for grading.
- Task sandboxes have internet access (as in the original runs).

## Left

- Paid runs with real agents: a 5-attempt pilot of one vendor setup and one self-hosted setup against the published rows (to confirm the port reproduces them within noise on the unchanged tasks, and to see how much the eight stricter graders move the changed ones).
- The torchtitan tasks' GPU checks (above) and an alternative fix for each; a different valid solution for `ray-exactly-once` (an independent exactly-once design, e.g. idempotent per-shard results committed atomically) was not written.
- Network: task sandboxes on Modal have internet, and the original runs found agents looking up public benchmarks. These tasks are new and unpublished until this repository, so an agent could now find the reference fixes here; grep transcripts for `agent-benchmarks`, or add an `[agent]` network allowlist to the tasks and check that the environment you run on enforces it.
- `harbor check` / `harbor analyze` (paid LLM reviews of the tasks and of trials) were not run.
