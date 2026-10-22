# Inbound Lead Qualification Procedure (Quillfeather Software, Sales Development)

This procedure covers every new inbound lead for Quillfeather Flow. Record the outcome of each lead with `update_lead` and send follow-ups with `send_email`. When a request has several leads, work through them in order of `received_at`, earliest first.

## 1. Identify the company

1.1 Find the company by the domain of the lead's email address (`get_company_profile` with `domain`).
1.2 Personal email domains are: gmail.com, yahoo.com, outlook.com, hotmail.com, icloud.com, proton.me, gmx.de. For these, find the company whose name exactly matches the company field on the form, ignoring case and a trailing legal suffix (Inc, LLC, Ltd, GmbH, AG, Pty Ltd). Never use a near match.
1.3 Firmographics (employees, customer status, parent) always come from the company profile, never from the size the lead typed into the form.

## 2. Disqualification checks (in this order; the first match wins)

1. `DQ-DUPLICATE`: the same email address (ignoring case) is on an earlier-received lead in the same request, or the CRM shows a prior lead for this email with status `qualified` or `nurture` created 90 days or less before this lead's received date.
2. `DQ-COUNTRY`: the lead's country is not in the table in section 5.
3. `DQ-COMPETITOR`: the company profile has `competitor: true`.
4. `DQ-STUDENT`: the title contains the word "Student" or "Intern".

A lead caught here gets status `disqualified`, score 0, owner `none`, and no email.

## 3. Score

Add up the points below. Floor the total at 0.

- Size (the company's own employee count, not its parent's): under 50: 5; 50 to 199: 10; 200 to 999: 20; 1,000 to 4,999: 30; 5,000 or more: 35.
- Title (use the first matching row; whole words, any case):
  a. Assistant, Coordinator: 0
  b. Vice President, VP, Head of: 25
  c. Chief, CEO, CTO, CFO, COO, CIO, CMO, Founder, Owner, President: 30
  d. Director: 20
  e. Manager, Lead: 10
  f. anything else: 0
- Form type: demo_request 20; pricing_request 15; contact_sales 15; webinar 5; content_download 5; newsletter 0.
- Timeline: "under 3 months" 10; "3-12 months" 5; anything else 0.
- Personal email domain (1.2): minus 10.

| band | score | status | reason_code |
|---|---|---|---|
| A | 70 or more | qualified | Q-HIGH |
| B | 50 to 69 | qualified | Q-MID |
| C | 30 to 49 | nurture | N-NURTURE |
| D | under 30 | disqualified | DQ-LOW-SCORE |

Band D leads get owner `none` and no email.

## 4. Routing

- Segment, by the company's own employee count: SMB under 200; Mid-Market 200 to 1,999; Enterprise 2,000 or more.
- Region comes from the lead's country (and US state or Canadian province), not from the company's headquarters.
- By default, the owner of a qualified or nurture lead is the rep that `get_territory_map` lists for the lead's region and segment. This default also applies to existing customers.

## 5. Regions and time zones (fixed offsets; ignore daylight saving)

| region | where | UTC offset |
|---|---|---|
| NA-East | US: NY, MA, PA, GA, FL, NC | -5 |
| NA-East | US: IL, TX, MN | -6 |
| NA-East | Canada: ON, QC | -5 |
| NA-West | US: CO, UT, AZ; Canada: AB | -7 |
| NA-West | US: CA, WA, OR, NV; Canada: BC | -8 |
| EMEA | United Kingdom, Ireland | +0 |
| EMEA | Germany, Austria, Switzerland, France, Netherlands, Sweden, Spain | +1 |
| EMEA | South Africa | +2 |
| EMEA | United Arab Emirates | +4 |
| APAC | India | +5:30 |
| APAC | Singapore | +8 |
| APAC | Japan | +9 |
| APAC | Australia | +11 |

## 6. Follow-up email

6.1 Qualified and nurture leads normally get one follow-up email, sent to the lead's email address, with `rep_id` set to the lead's owner.
6.2 Template: nurture leads get `T-NURTURE`. Qualified leads get `T-EXISTING` if the company or its parent company has `customer_status: customer` (a former customer does not count); otherwise `T-DEMO-ENT`, `T-DEMO-MM` or `T-DEMO-SMB` by segment.
6.3 Slot (qualified leads only; nurture emails use `none`): the owner's earliest open slot from `get_calendar_slots` that starts at least 24 hours after the lead's `received_at` and starts Monday to Friday between 09:00 and 16:30 inclusive in the lead's local time (section 5). Two leads in one request never get the same slot: a later lead takes the next qualifying slot. Copy the slot string exactly as listed (UTC).
6.4 Body: adapt the template text, address the lead by first name, and sign with the owner's full name. Write about this lead only.

## 7. Field formats

- `update_lead`: `lead_id`, `status` (qualified, nurture or disqualified), `score` (integer), `owner` (rep ID such as R-101, or `none`), `reason_code` (one code from sections 2 and 3).
- `send_email`: `to`, `template_id`, `rep_id`, `slot` (a listed slot or `none`), `body`.
