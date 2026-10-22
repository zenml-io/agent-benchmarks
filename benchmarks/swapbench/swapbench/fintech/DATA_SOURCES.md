# Fintech domain: external data we can build on (checked Oct 14, 2026)

## Use

1. **CFPB Consumer Complaint Database** ([consumerfinance.gov](https://www.consumerfinance.gov/data-research/consumer-complaints/)).
   US government open data ("freely available for anyone to use"), with no formal license; cite it.
   Narratives are opt-in and PII-scrubbed.
   - **Volumes for checking accounts (402k complaints):**
     - "Transaction was not authorized": 37k
     - Overdraft fees: 21k
     - NSF fees: 5k
     - Debit/ATM card problems: 50k
     - Banking errors: 24k
     - Credit cards (all issues): 351k
   - **How we use it:**
     - Weight the scenario mix by these counts.
     - Seed customer phrasing and personas from narratives, via LLM paraphrase.
     - Publish only generated scenarios plus complaint IDs and a citation, never the narratives.
2. **Reg E §1005.6 / §1005.11** and **Reg Z §1026.13** (CFPB, public law).
   - Reg E unauthorized liability: $50 if reported within 2 business days; $500 later; unlimited after 60 days from the statement.
   - Reg E error resolution: 60-day notice; resolution in 10 business days, or 45 days with provisional credit.
   - Reg Z billing errors: 60 days.
   - Next policy version: statement-date windows, the liability tiers, provisional credit, and edge cases by construction (day 59 vs day 61, debit vs credit card).
3. **BANKING77** ([HF](https://huggingface.co/datasets/PolyAI/banking77), CC BY 4.0; 13k queries, 77 intents) and
   **CLINC150** ([HF](https://huggingface.co/datasets/clinc/clinc_oos), CC BY 3.0). Real opening utterances, and out-of-scope or distractor requests.
4. **MCC codes** ([github](https://github.com/greggles/mcc-codes), Unlicense) and PaySim / IBM AMLSim
   (AMLSim generator: Apache-2.0). Merchant categories plus amount and time distributions for the synthetic bank.
   Use statistics only, not rows, until the Kaggle licenses are confirmed.
5. **tau2 banking_knowledge** (MIT). A comparison point and anti-overlap check, not a source.
   - 698 documents, retrieval-based policy, ~97 tasks.
   - Our domain differs: the policy is given, and the focus is money-moving actions graded by end state.

## Avoid for anything we publish

- **IEEE-CIS** (competition terms).
- **CRMArena-Pro** (CC BY-NC).
- **Bitext** (CDLA-Sharing) and **SGD** (CC BY-SA): share-alike would apply to derived data.
- **TalkMap**: low realism.
