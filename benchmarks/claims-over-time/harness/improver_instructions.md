# Improver instructions (one round)

Both improvers receive this text unchanged, except for the single line marked `ARM-SPECIFIC`, which says where each one reads the recorded runs and how it reruns the agent (Codex: the `claims-rerun` tool; the ZenML Pro agent: Kitaru experiments). `scripts/round.py` fills in the values in `{braces}` before each round and gives the improver everything below the line (the `ARM-SPECIFIC:` label included).

---

You maintain a claims-review agent for a health insurance regulator. In each case a health plan denied a treatment, the patient appealed, and the agent decides whether the denial should be upheld or overturned. Independent reviewers later decide these appeals, and that ruling is the correct answer.

The agent has just finished batch {round} of {total_rounds}: {batch_size} new appeals. It has now decided every appeal of batches 1 to {round}. Your job this round is to propose **one** change that makes the agent decide future appeals more accurately.

What you have:

- The agent's code and configuration, version {current_version}, in `{agent_dir}`. Its README says how to run it.
- The recorded runs of the agent on every appeal of batches 1 to {round} ({runs_total} appeals): every model call, tool call and final decision. Each batch was decided by the agent version that was current at the time.
- The true ruling for {revealed_count} randomly chosen appeals from each batch so far, {revealed_total} in total: the `truth` field in `{cases_file}`. Rows without `truth` are appeals whose ruling is not available to you.
- ARM-SPECIFIC: {arm_access}

Rules:

1. **Budget.** You may rerun the agent on the revealed appeals at most {rerun_budget} times this round, and you have {minutes} minutes. Plan your reruns; when they are used up, decide with what you have. Every rerun is counted after the round, and reruns over budget are reported.
2. **One change.** It can touch the instructions, the tool descriptions, how the agent uses its tools, the model settings, or the code in `{agent_dir}`. It must be one coherent idea that you can describe in two or three sentences. Do not change the case data, the precedent library or the scoring. The model the agent calls is set by the coordinator: do not change `model` or `base_url_env` in `config.toml`; a version that changes them is not shipped. Leave your version in `{agent_dir}`: that directory is what the coordinator takes.
3. **How your change is judged.** After you finish, the coordinator runs your version and the current version three times each {approval_rule}. Your version ships only if its mean balanced accuracy over those runs (balanced accuracy is the average of accuracy on upheld appeals and on overturned appeals) is at least as high as the current version's. Otherwise the current version stays. The coordinator also reports how many appeals each version wrongly denied, wrongly approved and left undecided. Either way, the next batch is scored on appeals no one has seen.
4. **No outside lookups.** Every ruling is public online, so you have no internet access beyond the model API (and the Kitaru workspace, if the line above names one). Do not try to find rulings elsewhere.
5. **Write down your change** in `{agent_dir}/CHANGE.md`: what you changed, the evidence that led you to it (which appeals, what pattern), and what you expect it to fix.

You may also decide that no change is worth making this round. In that case, write `NO CHANGE` and your reasoning in `CHANGE.md`.
