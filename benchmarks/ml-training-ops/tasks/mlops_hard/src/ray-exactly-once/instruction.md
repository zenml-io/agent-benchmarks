# Exactly-once payment totals on Ray, under worker crashes

`/app/pipeline.py` computes per-user payment totals from the event shards in `/app/data/shards/`
on Ray. Preprocessor actors stream transformed events into a named, detached actor `totals`
(namespace `payments`). The finance dashboard reads it live with `get_all()` while the job runs,
and the driver writes the final result to `out/totals.json` (`{user: usd_cents}`). Business rules
are in `transform.py`. Don't change them.

The numbers are wrong, and they get worse whenever the cluster has a bad day:
- upstream delivers events at least once, so the same event id can appear more than once, in the
  same or different shards. Each event id must count once.
- when a worker process dies (OOM-killer, spot node reclaimed), Ray restarts actors and retries
  calls, and totals drift: sometimes up, sometimes down. Sometimes the job dies, or hangs.

Make the pipeline exactly-once and crash-proof:
- `out/totals.json` must be exactly right after every run, even when any Ray worker process (actors
  or tasks, including the `totals` actor) is `SIGKILL`ed at any moment, any number of times.
- The live totals from `get_all()` must never exceed the true total for any user at any moment.
  Lower is fine while the job runs; the finance team alerts on overcounts.
- The job must not hang. A clean run should still take well under a minute.
- Keep using Ray for the parallel work: workers in Ray processes plus the `totals` actor, with that
  name, namespace and `get_all()` method. The job is started with `python pipeline.py` and connects
  to the cluster in `RAY_ADDRESS` (or starts a local one).

`chaos.py` kills one random Ray worker process. Use it to try things out.
