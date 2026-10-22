# Cut the cost of our support agent, without making it worse

Our customer-support agent for the online store handles order cancellations, modifications,
returns and exchanges. It runs on `gpt-5-2025-08-07`, and that snapshot is being retired on
Dec 11. The agent is also expensive. We want to move it to something that costs **at most half
as much per conversation**, but only if it doesn't get worse.

## What you have

- **The production agent** in `/opt/tau2`, a copy of the `tau2` framework. The agent is tau2's
  `llm_agent` on the `retail` domain:
  - its system prompt is `/opt/tau2/data/tau2/domains/retail/policy.md`;
  - its tools work against a simulated store database, so nothing you do here touches real customers.
- **A replay setup.** Conversations can be replayed with a simulated customer, which in production
  testing is always `anthropic/claude-haiku-5-5` with `--user-llm-args '{}'`. Example:
  ```
  cd /opt/tau2 && tau2 run -d retail --agent-llm <model> --agent-llm-args '{}' \
    --user-llm anthropic/claude-haiku-5-5 --user-llm-args '{}' --task-split-name train \
    --num-trials 1 --max-concurrency 8 --save-to /tmp/runs/<name>
  ```
  Model names are litellm names. tau2 grades each replayed conversation 0/1 by checking the final
  database state and the required actions, and reports cost per conversation.
- **Production traces** in `/app/traces/visible/`: one OpenTelemetry GenAI trace per conversation
  (`*.otlp.json`), plus `index.jsonl` with each conversation's outcome (reward 1 = handled
  correctly), cost and tool use. The incumbent ran them, one conversation per scenario in tau2's
  `train` split. They are a sample of real traffic.
- **Prices** for candidate models in `/app/prices.json` ($ per 1M tokens).
- **API keys** for OpenAI and Anthropic, already in the environment.

## Budget

- About **$5** of model inference for your experiments (please track it).
- About **2 hours**.

## Rules

- You may change the model and its decoding settings.
- You may append instructions to the agent's system prompt. You may not change the tools, the
  database or the grading.
- You may use only the models listed in `/app/prices.json`.

## What to deliver

Write two files.

`/app/submission/config.yaml`:
```yaml
model: <litellm model name, exactly as production should call it>
llm_args: {}            # decoding settings passed to the model, if any
policy_suffix: ""       # text appended to policy.md, if any
```

`/app/submission/verdict.json`:
```json
{
  "decision": "SAFE | UNSAFE | INSUFFICIENT_EVIDENCE",
  "expected_cost_reduction": 0.0,
  "expected_success_rate_change_pts": 0.0,
  "interval_pts": [0.0, 0.0],
  "known_breakages": ["..."],
  "evidence": "how you reached the decision"
}
```

What the decisions mean:
- **SAFE:** you recommend we switch production to this config now. Its success rate on our
  real traffic is at most **5 points** below the current agent's, and it doesn't make more wrong
  database changes (wrong refunds, wrong cancellations).
- **UNSAFE:** the cheaper config is worse; we should not switch.
- **INSUFFICIENT_EVIDENCE:** you couldn't tell within the budget.

We will check your decision against a larger set of production conversations that you don't
have. A wrong SAFE is the costly mistake: it ships a worse agent to customers. A wrong UNSAFE
leaves money on the table.
