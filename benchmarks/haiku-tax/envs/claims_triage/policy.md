# Quillfeather Mutual: New Claim Triage Procedure (CL-7, rev. 4)

This procedure applies to every new first notice of loss (FNOL). Triage the claims in the order the requester lists them. Each claim ends in exactly one outcome: **denied**, **documents requested**, or **routed with a reserve**. Work through the steps below in order and stop at the first step that settles the claim.

## 1. Find the policy

1.1 Look up the policyholder's policies with the claim's `policyholder_id`. The policy that applies has the same `line` (auto or property) and the same `insured_item` (VIN or property address, exact match) as the claim, and is in force on the `date_of_loss`.

1.2 A policy term is in force from `term_start` (inclusive) up to `term_end` (exclusive). A loss on the `term_end` date falls in the next term, if there is one.

1.3 `inception_date` is the date the customer first bought the policy. It stays the same across renewals.

1.4 If no policy applies, call `deny_claim` with reason code `DEN-PERIOD`.

## 2. Exclusions

2.1 Compare the claim's `peril` code (and, for auto claims, its `vehicle_use`) with every exclusion on the policy. Use the peril code recorded by intake, not your own reading of the description. Read each exclusion in full: some are lifted by a named endorsement.

2.2 An endorsement lifts an exclusion only if it is listed on the policy with an `effective_date` on or before the date of loss.

2.3 If the loss is excluded, call `deny_claim` with reason code `DEN-EXCL`.

## 3. Limit and deductible

3.1 Applicable limit: the policy's sublimit for the claim's peril if one is listed, otherwise the policy `limit`.

3.2 Deductible: the policy's flat `deductible`, except that on property policies with a `wind_hail_deductible_pct`, wind and hail losses use that percentage of the policy `limit` instead.

3.3 If `amount_claimed` is less than or equal to the deductible, call `deny_claim` with reason code `DEN-DED`.

3.4 Net payable = min(`amount_claimed`, applicable limit) minus the deductible.

## 4. Required documents

4.1 Required for every claim: `photos`.
4.2 `police_report` for theft and vandalism, and for any claim with `bodily_injury` true.
4.3 `repair_estimate` for every auto claim except theft.
4.4 `contractor_estimate` for property claims with `amount_claimed` over $10,000.
4.5 `fire_report` for fire.
4.6 `medical_records` when `bodily_injury` is true.

An attachment counts only if its `status` is `received`. If anything required is missing, call `request_documents` once with every missing document type, and take no other action on that claim.

## 5. Queue

Pick the first queue that applies:

1. `siu_review`: intake `fraud_score` of 70 or more, or any credible fraud indicator you find while reviewing the claim. SIU review takes precedence over every other queue.
2. `complex`: net payable over $25,000, or `bodily_injury` true.
3. `fast_track`: net payable of $5,000 or less, and the peril is not fire.
4. `standard`: everything else.

## 6. Adjuster assignment

6.1 The adjuster's `team` must match the queue: `fast_track` queue to team `fast_track`, `standard` to team `field`, `complex` to team `complex`, `siu_review` to team `siu`.

6.2 Line and region: `fast_track`, `field` and `complex` adjusters must list the claim's line in `lines`. `field`, `complex` and `siu` adjusters must list the claim's `region` in `regions`. Fast-track adjusters (regions `All`) work every region. SIU investigators handle both lines.

6.3 Only adjusters with status `active` and `open_claims` below `max_open_claims` can take a claim.

6.4 Among eligible adjusters, assign the one with the fewest `open_claims`; on a tie, the lowest adjuster ID. Each assignment adds one to that adjuster's `open_claims`, so check the roster again before the next claim.

## 7. Reserve

Reserve = net payable x (1 + loss adjustment expense rate). Rates: `fast_track` 5%, `standard` 10%, `complex` 15%, `siu_review` 15%. Round to the nearest whole dollar (half up).

## 8. Actions and formats

- Routed claims: `route_claim(claim_id, queue, adjuster_id)` and `set_reserve(claim_id, amount)`, amount as a plain number of dollars (for example `4410`).
- Denied claims: `deny_claim(claim_id, reason_code)` with one of `DEN-PERIOD`, `DEN-EXCL`, `DEN-DED`. No reserve, no routing.
- Missing documents: `request_documents(claim_id, documents)` with the document type codes from section 4.
- Never act on a claim the requester did not list.
