# SwapBench scenario data

## Public scenario sets (`public/`)

Generated for anyone to use, from a seed that is **not** used by any hidden set (31415):

| set | scenarios | world | regenerate |
|---|---|---|---|
| `public/fintech` | 500 (60% multi-request) | fictional bank "Northbank": 650 synthetic customers, 21k transactions | `python -m swapbench.fintech.gen out --n 500 --seed 31415 --splits public:500 --prefix pf` |
| `public/retail` | 500, 17 kinds | tau2-bench retail store (MIT) with generated customer requests | `python -m swapbench.gen_retail <tau2> out --n 500 --seed 31415 --splits public:500 --prefix pg` |

- **Files:** each set has `tasks.json`, `split_tasks.json` and `policy.md`, plus `db.json.gz` (gunzip before use).
- **Grading:** every scenario carries its ground truth by construction: the gold tool calls, graded by end state (`reward_basis: ["DB"]`).
- **Fintech data:** fully synthetic, with no real people or institutions.
- **Retail data:** the product catalogue and the base users and orders come from [tau2-bench](https://github.com/sierra-research/tau2-bench) (MIT licence, commit dd8757d); the requests are generated.
- **Generator fixes since the evaluation sets were made:** both public sets come from the current generators, which include the retail fix from `experiments/scenario_review.md` (cancellation requests on delivered orders).

How to run an agent on them (from the benchmark directory, after `uv sync`; `tau2` is `.venv/bin/tau2`):

```
gunzip -k data/public/fintech/db.json.gz
SWAPBENCH_FINTECH_DIR=data/public/fintech scripts/tau2x run -d fintech --task-split-name public ...
mkdir -p /tmp/retail/tau2/domains/retail && cp data/public/retail/* /tmp/retail/tau2/domains/retail/ && gunzip /tmp/retail/tau2/domains/retail/db.json.gz
TAU2_DATA_DIR=/tmp/retail tau2 run -d retail --task-split-name public ...
```

## Hidden sets v2 (for leaderboards; not released)

Generated Oct 14 from **secret seeds** that appear nowhere in this repository. Each domain has 500 scenarios: 60 visible, 240 hidden and 200 pool. They use the current generators.

| check | fintech | retail |
|---|---|---|
| gold action lists that execute cleanly | 500 / 500 (validated during generation) | 500 / 500 |
| customers shared with other sets | 0 with the public set, 0 with v1 | uses tau2's public store, like every retail set |
| scenario texts shared with other sets | 9 with the public set, 6 with v1: generic templates naming no customer | 0 with the public set, 0 with v1 (overlaps removed after generation) |

- **The retail world is tau2's public store,** so for retail the hidden part is the 500 generated requests.
- **Storage:** the sets and their seeds are kept only in the maintainers' private storage, with `SHA256SUMS`; they are not in this repository. Leaderboard operators and reviewers can request evaluation access from the maintainers (see the benchmark README).

| file | sha256 |
|---|---|
| fintech `tasks.json` | `0c59540212a945f6a24bc89cd689514d7853dc2589a8c701575ce4ec7a138dd1` |
| fintech `split_tasks.json` | `42ea071d1d5bf557d47029e4b3fdbe22a30207d1fc3fbfe6f8ed6b98b6fcb356` |
| fintech `db.json` | `481d9b997913709168c4c01e89bebd316be2a7d5b5a486c90949ebef14d9931f` |
| retail `tasks.json` | `640dcabb3fbb55a20abdfe3ad31cb8a41fb678c1fe3df817c5d13c883babc075` |
| retail `split_tasks.json` | `f7927265c74a9b8d4905ec7d72632365bd1cf5f2efc8afb4875bc4e41d2d42f3` |
| retail `db.json` (unmodified tau2 store) | `413a65160adbdb5fde0ffc0015c49b6d70250b10c18128de169b597af7766765` |

Rotate them per leaderboard release: generate with new secret seeds, publish only the hashes, and keep the seeds out of the repo.

## Hidden sets v1: the evaluation sets behind the published numbers (retired for leaderboards)

All results in `results/runs/` and `experiments/` use two 500-scenario worlds:
- 60 visible scenarios;
- 200 pool scenarios;
- 240 hidden scenarios.

They are not released here, so the hidden numbers can be re-checked later against untouched data. Their SHA-256:

| file | sha256 |
|---|---|
| fintech `tasks.json` | `66874423a4621e9147638c5c0a15904b69eb9edb551e4c6f881635fa045b1fa3` |
| fintech `db.json` | `230dafa82e9015da2cc74f4ad8913fabd4cc1bf926846d789112679e7efec2d8` |
| retail `tasks.json` | `7281917b40de4e1b83a43378d3a62f0ca05fc495669dcba71c450a017898271a` |
| retail `db.json` | `413a65160adbdb5fde0ffc0015c49b6d70250b10c18128de169b597af7766765` |

**Caveat: these v1 sets were hidden from the agents under test, but their seeds sit in the private research repo's history, which several people can read.** They are retired for leaderboard use; use v2 above.
- Both were made with the generators in this repo, from seeds recorded in the private research repo's history (not published here). The current generators with the documented default seed do not reproduce them (checked 2026-10-22: different hash).
- So they protect against an agent peeking during a run, not against someone with access to that history. Reviewers who need them to rerun the published numbers can request them from the maintainers.
- A public leaderboard should use fresh hidden sets from secret seeds held outside the repo, rotated per release, and should publish only their hashes.

## Licence

The repository has no licence yet; the owner should choose one before making it public. The tau2-bench parts of the retail world remain under tau2-bench's MIT licence, which requires keeping its copyright notice.
