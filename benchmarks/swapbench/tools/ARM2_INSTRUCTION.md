
## Verification toolkit

You also have `sb`, our model-migration toolkit (`sb --help`). It runs the production agent with the
production customer simulator and mocked tools, and it compares runs properly:

- `sb replay --name NAME --model M [--llm-args JSON] [--policy-suffix FILE] [--split train|pool]`
  replays a config on the scenarios you have (`train` = the 60 traced conversations).
- `sb compare --candidate NAME [--baseline traces|RUN]` pairs scenarios with the baseline (default:
  the incumbent's production traces) and reports the success-rate change with a 95% interval, the
  change in wrong database writes, cost per conversation, and a gate: SAFE, UNSAFE or
  INSUFFICIENT_EVIDENCE under the 5-point margin.
- `sb pool`: 200 more recent conversations' scenarios with no incumbent traces (split `pool`). If 60
  scenarios are not enough to decide, replay the incumbent and the candidate on (part of) the pool and
  compare them with `--baseline <incumbent run>`.
- `sb runs` lists your runs and their cost.

Replaying the incumbent costs about $0.15 per conversation; cheap candidates cost a few cents.
