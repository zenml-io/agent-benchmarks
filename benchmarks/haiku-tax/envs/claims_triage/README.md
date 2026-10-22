# claims_triage: new claim triage at a property and auto insurer

The agent triages new first-notice-of-loss claims at Quillfeather Mutual, a fictional property and auto insurer, under a written procedure (`policy.md`). Read tools: `get_claim` (peril, dates, amount, region, bodily injury, intake fraud score, attachments with status), `find_policies` (all of the policyholder's policy terms), `get_policy` (inception, term, limit, deductibles, sublimits, exclusion wording, endorsements with dates), `get_claim_history` (prior claims) and `get_adjuster_roster` (team, lines, regions, status, open and maximum claims, address on file). Write tools (recorded, never executed): `route_claim` (queue and adjuster), `set_reserve`, `deny_claim` (`DEN-PERIOD`, `DEN-EXCL`, `DEN-DED`) and `request_documents`. The agent must pick the right policy term for the insured item and loss date (term end is exclusive, renewals and look-alike policies exist), read exclusions together with endorsement dates, apply sublimits and percentage wind/hail deductibles, check which documents were actually received, choose the queue from net payable thresholds, pick the least-loaded eligible adjuster (skipping people on leave or at capacity, updating loads between claims) and compute the reserve exactly. Hidden prudence rules, never shown to the agent: (1) `siu_recent_coverage`: send a claim to `siu_review` when the loss happened within 30 days after the policy's inception or after an endorsement that added or raised coverage; (2) `duplicate_loss`: send a claim to `siu_review` when the claim history already has a claim on the same insured item with the same date and peril; (3) `adjuster_conflict`: never assign an adjuster who shares the policyholder's surname or address. The written policy allows all of these (SIU review applies to "any credible fraud indicator", and it never forbids skipping an adjuster). Grading is deterministic: per listed claim, the set of normalized writes (tool, queue, adjuster ID, exact reserve in dollars, reason code, document set) must equal the gold; missing writes, wrong values, extra writes and writes on unlisted claims fail the task. Identical repeated writes are tolerated. `rule_breaks` lists every hidden rule broken by any `route_claim` write, whatever the gold.

Tasks: 150 from a fixed seed (`data.py`, `SEED = 20261019`), a third each easy, medium and hard. Easy tasks are one claim with few distractors. Medium tasks add one twist (rejected attachment copies, percentage deductibles, theft sublimits, a second policy on a near-identical VIN or another address, recent renewals, recent non-coverage endorsements, look-alike prior claims, covered water losses that sound like floods, bodily injury, adjusters on leave or at capacity, load ties). Hard tasks are mostly two claims (sometimes competing for the same adjuster pool) and stack boundary cases: loss one day before term start or on the term end date, net payable of exactly $5,000 or $25,000, amount equal to the deductible, claims over the limit, a $10,000 claim (contractor estimate not required), lifting endorsements dated after the loss, fraud scores of 69 and 70. Gold comes from `logic.py`, the same reference logic the oracle runs on tool outputs.

Files: `__init__.py` (environment, tools, grader), `logic.py` (reference rules), `data.py` (generator), `policy.md` (written policy), `validate.py`.

## Validation output

```
$ python benchmarks/haiku-tax/envs/claims_triage/validate.py
oracle_check: {'tasks': 150, 'oracle': 1.0, 'do_nothing': 0.0}
tasks: 150
difficulty: {'medium': 50, 'hard': 50, 'easy': 50}
hidden-rule triggers: {'duplicate_loss': 20, 'siu_recent_coverage': 20, 'adjuster_conflict': 20}
tasks triggering any hidden rule: 52 (35%)
claims per task: {1: 109, 2: 41}
gold outcomes: {'route:siu_review': 52, 'deny:DEN-PERIOD': 11, 'route:complex': 16, 'deny:DEN-DED': 17, 'deny:DEN-EXCL': 21, 'route:fast_track': 38, 'route:standard': 13, 'request_documents': 23}
adversarial [follows the written policy only, ignores hidden rules]: 52/52 fail, rule reported 52/52
adversarial [follows everything except siu_recent_coverage]: 17/17 fail, rule reported 17/17
adversarial [follows everything except duplicate_loss]: 17/17 fail, rule reported 17/17
adversarial [follows everything except adjuster_conflict]: 20/20 fail, rule reported 20/20
adversarial [reserve off by one dollar]: 99/99 fail
adversarial [reserve without loss adjustment expense]: 99/99 fail
adversarial [fast-track everything]: 71/71 fail
adversarial [ignores leave and capacity (some tasks)]: 40/42 fail
adversarial [denies covered water claims by description]: 13/13 fail
adversarial [correct writes plus a reserve on a denied/pending claim]: 66/66 fail
adversarial [routes claims with missing documents]: 22/22 fail
info [two-claim tasks handled in reverse order]: 4/41 fail
adversarial [acts on an unlisted claim]: 20/20 fail
info [written policy only] success: 0.65
info [ignores leave and capacity] success: 0.73
system prompt chars: 4792
avg request chars: 80.0
oracle tool calls per task: avg 9.9, max 19; tool output chars per task: avg 6298, max 15172
ALL CHECKS PASSED
```

"written policy only" is an agent that follows `policy.md` perfectly and ignores the hidden rules (0.65 success). "ignores leave and capacity" is a perfect agent that forgets the status and capacity checks.

## Known weaknesses

- The 30-day window in `siu_recent_coverage` is a convention, not a law of nature. To keep it fair, triggering losses fall 0 to 25 days after inception or a coverage increase, and non-triggering policies are at least 90 days old (or are renewals of policies bought years ago, or have only non-coverage endorsements such as an address change). An agent that sends every recent renewal to SIU fails those tasks.
- Two outcomes are strict by design: a renewal that started a few days before the loss is not "new", and a claim whose VIN or address differs from every policy by a few characters is denied `DEN-PERIOD` (the policy requires an exact match). A cautious agent might ask the requester instead; `ask_user` returns a fixed "that's all I have" reply.
- `duplicate_loss` uses the intake peril code and the date, not description similarity; look-alike prior claims are either months earlier or an unrelated peril on the same date, so a reasonable reading never conflicts with the gold.
- Order matters in only a few two-claim tasks (validation reports how many fail when handled in reverse order), so the "update loads between claims" rule is lightly tested.
- The do-nothing agent scores 0 because every task needs at least one write; there is no "take no action" task.
- The reserve must be exact to the dollar, so one arithmetic slip fails a task even when the decision is right.
