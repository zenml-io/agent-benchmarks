# Larkhaven Bank: Business Account Onboarding KYC Review Procedure

This procedure applies to every business account application you review. Larkhaven Bank and all companies, people, countries and registries in its files are fictional.

## 1. Scope and decision

1.1 Each request names one application and a review date. All date checks use the review date, not today's calendar date.

1.2 Record exactly one decision per application with one of these tools: `approve_application`, `request_more_info`, `escalate_to_compliance` or `reject_application`. Do not record a second decision.

## 2. Persons to verify

2.1 Verify every director listed on the application, whatever their ownership.

2.2 Verify every natural person whose effective ownership of the applicant is 25% or more (25% exactly counts).

2.3 Effective ownership through a company is the product of the percentages along the chain. A person holding 50% of a company that owns 50% of the applicant holds 25% of the applicant. Find the shareholders of a corporate owner with `check_registry` on that company's registration number; a chain can have more than one corporate layer.

2.4 Persons below 25% who are not directors need no identity document and no screening.

## 3. Matching records to persons

Names can be spelled differently across the application, documents, the registry and screening results (transliteration, hyphens, spaces, accents). Treat two records as the same person when the dates of birth are identical and the names are plausible spellings of the same name. Use the party IDs from the application in all item codes.

## 4. Required documents

4.1 Company registry extract dated no more than 90 days before the review date (90 days exactly is acceptable). None submitted: `MISSING_REGISTRY_EXTRACT`. Older: `STALE_REGISTRY_EXTRACT`.

4.2 Proof of business address dated no more than 90 days before the review date. None submitted: `MISSING_POA`. Older: `STALE_POA`.

4.3 A passport or national ID card for each person to verify. None submitted: `MISSING_ID:<party_id>`. An ID whose expiry date is on or before the review date is expired: `NEW_ID:<party_id>`.

## 5. Screening

5.1 Screen every person to verify with `screen_names`, using the name as written on the application.

5.2 A result is a confirmed match only when its score is 85 or higher **and** its date of birth is identical to the person's date of birth. Ignore every other result.

5.3 Confirmed match on the SANCTIONS list: reject with `SANCTIONS_MATCH`. Confirmed match on the PEP list: escalate with `PEP_MATCH`.

## 6. Company and jurisdiction

6.1 Look up the applicant with `check_registry`. The live registry status is authoritative over any extract. If the status is not `active`, reject with `COMPANY_NOT_ACTIVE`.

6.2 Look up the applicant's country with `get_country_risk`. `prohibited`: reject with `PROHIBITED_JURISDICTION`. `high`: escalate with `HIGH_RISK_JURISDICTION`.

## 7. Decision order

1. If any rejection reason applies, reject. If several apply, use the first in this order: `PROHIBITED_JURISDICTION`, `COMPANY_NOT_ACTIVE`, `SANCTIONS_MATCH`.
2. Otherwise, if any escalation reason applies, escalate with every applicable escalation code. Do not also request documents; compliance collects them.
3. Otherwise, if any item is missing, call `request_more_info` listing every item code.
4. Otherwise approve with a risk tier.

## 8. Risk tier (approvals only)

- `high`: the declared activity is on the high-risk list: money transfer services, virtual asset exchange, precious metals trading, online gaming.
- `medium`: not high, and at least one of: country risk `medium`; expected monthly volume above USD 200,000; a company anywhere in the ownership chain.
- `low`: everything else.

## 9. Code table

Request items: `MISSING_REGISTRY_EXTRACT`, `STALE_REGISTRY_EXTRACT`, `MISSING_POA`, `STALE_POA`, `MISSING_ID:<party_id>` (no identity document for the person), `NEW_ID:<party_id>` (the person must supply a new identity document).

Escalation codes: `PEP_MATCH`, `HIGH_RISK_JURISDICTION`, `REGISTRY_MISMATCH` (application details conflict with the company registry), `ACTIVITY_VOLUME_MISMATCH` (expected account activity is implausible for the business).

Rejection codes: `PROHIBITED_JURISDICTION`, `COMPANY_NOT_ACTIVE`, `SANCTIONS_MATCH`.

Write codes in upper case exactly as shown, with party IDs such as `NEW_ID:PTY-1234`.
