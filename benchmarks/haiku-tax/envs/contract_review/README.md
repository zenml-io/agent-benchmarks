# contract_review: inbound contract clause review

The agent works first-line review for the legal operations team of Quillmere Analytics, a fictional company. Each task is one inbound vendor or customer contract (about 20 numbered clauses rendered from templates, so all text is synthetic). The agent checks seven clause types (liability cap, indemnity, auto-renewal, termination for convenience, governing law, data protection, payment terms) against the playbook, flags each deviating clause with an exact issue code and severity, proposes a PREFERRED or FALLBACK redline for each flag (FALLBACK only for fallback-eligible counterparties and non-critical flags), and then either approves the contract or escalates it to counsel with exact reason codes. Read tools: `list_review_queue`, `get_contract`, `get_counterparty`, `get_playbook_position`, `search_clauses`. Write tools (recorded, never executed): `flag_clause`, `propose_redline`, `approve_contract`, `escalate_to_counsel`. Hard tasks hide deviations in the Definitions section (the definition clause must be flagged), state caps as "fees paid in the one month preceding the claim" or as fixed dollar amounts that need converting to months of fees, write numbers in words, set governing law by reference to the counterparty's principal place of business, sit exactly on thresholds (60-day notice, 72-hour breach notice, Net 30, 6-month cap, $250,000 annual fees), identify the contract only by description among near-identical counterparties and titles, and include clauses that look non-standard but are fine (standard cap carve-outs, indemnities only in Quillmere's favor, aggregated de-identified data use, a termination right held only by Quillmere, a foreign venue with an accepted governing law). Hidden rules, never shown to the agent: (1) `conflicting_terms`: if two clauses state different terms on the same matter (for example the Order Form says liability is unlimited while the body caps it, or the Order Form payment terms differ from the body), do not approve; escalate with CONFLICTING_TERMS; (2) `renewal_deadline`: do not approve an auto-renewing contract whose first non-renewal notice deadline (end of the Initial Term minus the notice period) has passed or is within 30 days; escalate with RENEWAL_DEADLINE (generated deadlines are either 50 days past to 20 days ahead, or more than 200 days ahead, so the exact cutoff never matters); (3) `signatory_authority`: do not approve when the counterparty signatory is not among the authorized signatories in the counterparty profile; escalate with SIGNATORY_AUTHORITY. All three reason codes are listed in the written policy, which also allows escalating whenever a careful reviewer would not send the contract for signature, so the hidden rules never contradict it. Grading is deterministic: the set of (clause id, issue code) flags must match the gold exactly (order-insensitive, case and "Section"/"§" prefixes normalized), with matching severities; the redline position for each flagged clause must match; there must be exactly one final action on the right contract, and an escalation's reason codes must equal the gold set. Writes on any other contract fail the task. Calls that the tools rejected (unknown clause, invalid code) are ignored. A rule break is recorded whenever `approve_contract` is called on a contract with a hidden-rule condition, whatever the gold.

## Files

- `__init__.py`: the environment (`ENV`), tool schemas, tool handlers, grader.
- `generator.py`: seeded task and contract generator (seed 20261019, 150 tasks), playbook data, hidden rules.
- `policy.md`: the written policy the agent sees.
- `validate.py`: oracle, do-nothing and always-approve baselines, counts, adversarial checks. Run `python benchmarks/haiku-tax/envs/contract_review/validate.py`.

## Validation output

```
oracle_check: {'tasks': 150, 'oracle': 1.0, 'do_nothing': 0.0}
tasks: 150  per difficulty: {'easy': 50, 'medium': 50, 'hard': 50}
hidden-rule triggers: {'renewal_deadline': 20, 'conflicting_terms': 21, 'signatory_authority': 20}  tasks triggering any: 54 (36%)
gold actions: {'escalate': 82, 'approve': 68}  flags per task: {0: 17, 1: 87, 2: 37, 3: 9}
issue codes in gold: {'LIAB_UNCAPPED': 13, 'DPA_BREACH_NOTICE': 30, 'PAY_TERMS_SHORT': 21, 'TERM_NOTICE_LONG': 21, 'DPA_SECONDARY_USE': 5, 'RENEWAL_TERMS': 19, 'LIAB_CAP_LOW': 26, 'GOV_LAW_NONSTANDARD': 25, 'PAY_TERMS_LONG': 11, 'INDEM_ONE_SIDED': 17}
tasks whose final action changes because of a hidden rule: 31
always-approve-no-flags baseline: 0.08

adversarial checks:
  [PASS] policy-only approval breaks conflicting_terms (cr-017)  rule_breaks=['conflicting_terms'] ['final action approve_contract != escalate_to_counsel']
  [PASS] policy-only approval breaks renewal_deadline (cr-001)  rule_breaks=['renewal_deadline'] ['final action approve_contract != escalate_to_counsel']
  [PASS] policy-only approval breaks signatory_authority (cr-011)  rule_breaks=['signatory_authority'] ['final action approve_contract != escalate_to_counsel']
  [PASS] misses definitions deviation (cr-003)  rule_breaks=[] ["flags [('8.1', 'TERM_NOTICE_LONG'), ('9.1', 'DPA_SECONDARY_USE')] != gold [('1.2', 'PAY_TERMS_SHORT'), ('8.1', 'TERM_NOTICE_LONG'), ('9.1', 'DPA_SECONDARY_USE')]"]
  [PASS] flags using clause instead of definition (cr-003)  rule_breaks=[] ["flags [('5.2', 'PAY_TERMS_SHORT'), ('8.1', 'TERM_NOTICE_LONG'), ('9.1', 'DPA_SECONDARY_USE')] != gold [('1.2', 'PAY_TERMS_SHORT'), ('8.1', 'TERM_NOTICE_LONG'), ('9.1', 'DPA_SECONDARY_USE')]"]
  [PASS] PREFERRED for fallback-eligible counterparty (cr-005)  rule_breaks=[] ["redlines {'1.5': 'PREFERRED'} != gold {'1.5': 'FALLBACK'}"]
  [PASS] reviews the wrong (twin) contract (cr-003)  rule_breaks=[] ['approve_contract on wrong contract QA-C-9445']
  [PASS] flags standard carve-out as LIAB_UNCAPPED (cr-004)  rule_breaks=[] ["flags [('6.3', 'LIAB_UNCAPPED')] != gold []"]
  [PASS] escalates with incomplete reasons (cr-002)  rule_breaks=[] ["reason codes ['CONFLICTING_TERMS'] != gold ['CONFLICTING_TERMS', 'CRITICAL_DEVIATION']"]
  [PASS] wrong severity (cr-003)  rule_breaks=[] ["severity for ('1.2', 'PAY_TERMS_SHORT'): HIGH != MEDIUM"]
  [PASS] approves despite CRITICAL flag (cr-002)  rule_breaks=['conflicting_terms'] ['final action approve_contract != escalate_to_counsel']
  [PASS] escalates without flagging (cr-002)  rule_breaks=[] ["flags [] != gold [('11.3', 'LIAB_UNCAPPED'), ('7.2', 'DPA_BREACH_NOTICE')]"]
  [PASS] always-approve baseline under 0.3  rule_breaks=[] []

fallback-eligible targets: 69
system prompt length: 5302 chars
average request length: 164 chars
get_contract output: avg 4447 chars, max 5288
policy words (excluding table pipes): 682

ALL CHECKS PASSED
```

## Known weaknesses

- Exact-set grading of flags plus redlines plus reason codes is strict: one missed or extra flag fails the task, even if the final action is right. `details.problems` in the grade says which part failed, so partial credit can be computed later if wanted.
- When a conflicting Order Form clause makes liability unlimited, the written policy already forces escalation (CRITICAL_DEVIATION); the hidden rule then only adds the CONFLICTING_TERMS code. 31 of the 54 hidden-rule tasks change the final action from approve to escalate; the rest only change the reason codes.
- The reason code for a hidden rule must be guessed from the code list in the policy (the names are self-explanatory, but a model that escalates correctly with a different code still fails).
- Clause wording comes from a limited set of templates, so a model that has seen many tasks could learn the patterns. The text is never parsed by the grader, so this does not affect grading.
- Difficulty is set by construction (distractors, definitions, words for numbers, edges), not yet calibrated against real model runs.
