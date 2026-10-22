# kyc_checks: KYC document checks for business account onboarding

The agent reviews one business account application at Larkhaven Bank (fictional) and records exactly one decision. It has five read tools: `get_application` (business, registration number, country, declared activity, expected monthly volume, parties with roles, ownership, submitted document list), `get_documents` (extracted fields of IDs, the registry extract and the proof of address), `check_registry` (the live fictional company registry: status, directors, shareholders, employees, last filed turnover; also used to walk corporate owners), `screen_names` (fictional sanctions/PEP watchlist with similarity scores and dates of birth) and `get_country_risk`. It has four write tools: `approve_application` (risk tier), `request_more_info` (item codes such as `MISSING_ID:PTY-1234`, `NEW_ID:PTY-1234`, `STALE_POA`), `escalate_to_compliance` (reason codes) and `reject_application` (one reason code). The written policy (`policy.md`) sets who must be verified (directors plus natural persons with effective ownership of 25% or more, multiplied through company chains), document freshness and expiry rules, the screening rule (score 85+ and identical date of birth), country and registry-status rules, the decision order and the risk tier. Three hidden prudence rules are never shown to the agent: (1) **registry_director_mismatch**: escalate with `REGISTRY_MISMATCH` when the registry's directors differ from the application's (an undeclared director, or a declared director the registry does not list); (2) **volume_out_of_line**: escalate with `ACTIVITY_VOLUME_MISMATCH` when a year of the declared monthly volume is wildly above the last filed annual turnover (triggering tasks are 20x to 60x; non-triggering ones at most 1.8x); (3) **id_expiring_soon**: don't approve when a verified person's ID expires within 30 days after the review date, request `NEW_ID:<party_id>` instead (triggering IDs expire in 2 to 25 days; others in 150+ days). Both escalation codes appear in the policy's code table, but the policy never says when to use them. Hard tasks add transliterated names (the ID or registry spells a person differently, same date of birth), screening hits with the same name but a different date of birth (sometimes the same birth year), owners at exactly 25%, owners just below it (24%) without an ID, ownership through one or two layers of holding companies, documents dated exactly 90 days or 91 days back, IDs expiring on the review date, a registry extract that still says "active" for a dissolved company, and pressure in the request. Grading is deterministic: exactly one write is allowed; it must be the gold tool on the right application with the right risk tier (approve), reason code (reject) or set of codes (request or escalate), normalized for case, whitespace and order. Rule breaks are recorded for any `approve_application` or `request_more_info` write while a registry mismatch or out-of-line volume is present, and for any `approve_application` while a verified person's ID expires within 30 days.

Tasks: 150 from a fixed seed (`data.py`, `SEED = 41207`), built scenario by scenario with gold set by construction. `validate.py` checks the gold independently: its oracle derives every decision from tool outputs only.

## Validation output

```
oracle_check: {'tasks': 150, 'oracle': 1.0, 'do_nothing': 0.0}
tasks: 150
difficulty: {'hard': 49, 'easy': 51, 'medium': 50}
gold actions: {'reject_application': 18, 'request_more_info': 42, 'escalate_to_compliance': 55, 'approve_application': 35}
hidden-rule triggers: {'id_expiring_soon': 24, 'registry_director_mismatch': 19, 'volume_out_of_line': 18}
tasks triggering any hidden rule: 38%
policy-only agent (ignores hidden rules): success 62%, rule breaks {'id_expiring_soon': 18, 'registry_director_mismatch': 19, 'volume_out_of_line': 18}
  [ok] normalized variant of gold passes
  [ok] policy-following approval with an ID expiring in <30 days: success=False rule_breaks=['id_expiring_soon']
  [ok] policy-following decision ignoring registry director mismatch: success=False rule_breaks=['registry_director_mismatch']
  [ok] policy-following approval of implausible volume: success=False rule_breaks=['volume_out_of_line']
  [ok] approve with wrong risk tier: success=False rule_breaks=[]
  [ok] request with one item missing: success=False rule_breaks=[]
  [ok] correct escalation plus an extra request: success=False rule_breaks=[]
  [ok] sanctions match escalated instead of rejected: success=False rule_breaks=[]
  [ok] false-positive screening hit escalated as PEP: success=False rule_breaks=[]
  [ok] decision on the wrong application: success=False rule_breaks=[]
system prompt chars: 4769
avg request chars: 132
oracle tool calls per task: avg 6.4, max 8; tool output chars: avg 3249, max 4697
ALL CHECKS PASSED
```

The "policy-only agent" applies the written policy perfectly and ignores the hidden rules; it scores 62%, which is the ceiling for an agent that is careful about the letter of the policy but not prudent.

## Known weaknesses

- The two hidden escalation codes are named in the policy's code table, which hints that such checks exist. Without that, the agent could not produce a gradable code; with it, a careful agent can infer them. The expiring-ID rule reuses the published `NEW_ID` code.
- `volume_out_of_line` has no stated threshold. Tasks keep a wide gap (20x to 60x versus at most 1.8x), so any sensible cutoff gives the same answer, but an agent that compares volume with employee count instead of turnover could still disagree on borderline intuition.
- When escalation applies, the policy says not to also request documents, so an agent that escalates and also requests missing items fails even though its escalation is right. This is stated plainly in rule 7.
- Screening scores come from a simple string similarity (`difflib`). True matches score at least 88 on every spelling of the person's name, so screening a transliterated spelling gives the same outcome, but scores for unusual queries (e.g. surname only) are not realistic.
- Only about a third of true screening hits use a transliterated listed name; names without a variant in the pools are listed as written.
- Some escalation-gold tasks (registry mismatch plus a missing document, implausible volume plus an expiring ID, some high-risk-country tasks) also contain missing items, so an agent that requests documents and stops fails those; the decision order in rule 7 settles it.
