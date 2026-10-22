# Loss became NaN: find the bad data before the restart

Our churn-model training job (8 data-parallel ranks, code in `/app/trainer/`, data in
`/app/data/shards/`) crashed with a NaN loss. The log is in `/app/logs/train.log`. Before we
restart from the last checkpoint we want to quarantine every bad row in the dataset, not just the one
that crashed this run. Otherwise the restart will crash again later in the epoch.

A row is bad if feeding it through our input pipeline (`trainer/data.py`, as configured in
`trainer/config.py`) produces a non-finite feature value for the model. Data that looks odd but goes
through the pipeline to finite features is not bad: the data team says several columns have
legitimate outliers and a few columns contain junk that the model never uses. Don't quarantine those
rows. We lose customers' data every time we do.

Write `/app/answer.json`:

```json
{
  "crash_shard": "<file name of the shard that produced the NaN in this run, e.g. shard-0001.npy>",
  "crash_rank": <int>,
  "crash_step": <int>,
  "bad_rows": {"<shard file name>": [<row indices within that .npy file, 0-based>], "...": []}
}
```

`bad_rows` must list every bad row in the whole dataset, and nothing else. Leave out shards with
no bad rows.
