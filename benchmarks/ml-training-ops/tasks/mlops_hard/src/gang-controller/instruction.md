# Make the gang scheduler production-ready

`/app/controller.py` is the v0 gang scheduler for our training cluster. Read `/app/README.md` for
the rules it must satisfy. It fails them badly: it crashes on API errors, leaves partial gangs
holding GPUs, and lets jobs starve.

Rewrite `Controller` in `/app/controller.py` so that it satisfies all the rules, robustly. We will run
it against the same simulator semantics on many cluster histories and cluster sizes you haven't
seen. Every run must pass, not just most of them. You can test with `python /app/run.py --seeds ...`.

Don't modify `kube/sim.py` or `run.py`: the grader uses its own pristine copies.
