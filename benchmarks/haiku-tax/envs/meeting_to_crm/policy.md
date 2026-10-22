# Brightwater Analytics: CRM update after a customer meeting (Sales Ops procedure, rev. 7)

Use this procedure when a rep asks you to update the CRM from a customer meeting. Do the whole update in one go; do not ask the rep to confirm. The meeting notes and the CRM hold everything you need.

## 1. Find the meeting and the opportunity

1.1 Read the notes with `get_meeting_notes`. The meeting date in the notes header is the anchor for every relative date.
1.2 Find the account's opportunities with `search_opportunities` and match on the account ID in the notes header (other accounts can have similar names). If the account has more than one open opportunity, update only the one the meeting was about, matching on the product discussed. Never change an opportunity that was not discussed, even if the notes mention it in passing.

## 2. Latest statement wins

When a figure or date is stated more than once, including corrections ("actually, make that Q3") and corrections by another speaker, use the last one stated by the customer side. Figures proposed only by Brightwater people (for example our list price) do not count.

## 3. Stage and probability

| Code | Stage | Entry criteria (must be met in this meeting) | Probability |
|---|---|---|---|
| S1 | Discovery | First qualified conversation | 10 |
| S2 | Qualified | Customer confirms budget exists and names who makes the decision | 20 |
| S3 | Solution Fit | Customer confirms the technical evaluation or pilot was completed successfully | 40 |
| S4 | Proposal | Customer has reviewed our written proposal and accepts the pricing structure | 60 |
| S5 | Commit | The decision maker verbally commits to buy at the stated amount and target close date | 80 |
| CW | Closed Won | Signed order form received | 100 |
| CL | Closed Lost | Customer chose another vendor or cancelled the project | 0 |

3.1 Move at most one stage per meeting, forward only, and only when the entry criteria of the next stage were met in this meeting. Otherwise leave the stage as it is.
3.2 Whenever you set the stage, set `probability` to the value in the table.
3.3 Use the stage codes exactly as written (`S4`, `CW`).

## 4. Amount

4.1 `amount` is the total first-year contract value in US dollars, as a plain number with no symbols or separators (e.g. `91800`).
4.2 "k" means thousand and "m" or "million" means million. Figures stated without a currency are US dollars.
4.3 Convert other currencies with `get_fx_rates` (amount times the rate to USD) and round to the nearest whole dollar.
4.4 Ignore figures about other vendors, past spend, discounts in percent and the account's other opportunities.
4.5 If no deal value was stated in the meeting, leave `amount` unchanged. When moving to CW, use the value on the signed order form if one is mentioned.

## 5. Close date

5.1 `close_date` is the date the customer expects to sign, in `YYYY-MM-DD`. If it was not discussed, leave it unchanged.
5.2 When moving to CW, set it to the date the signed order form was received.
5.3 Relative dates, counted from the meeting date:
- A weekday name ("Thursday") is the first such day strictly after the meeting date.
- "N weeks from <weekday>" is that weekday (as above) plus N times 7 days.
- "End of week" is the Friday of the meeting's week. "End of month" is the last day of the meeting's month; "end of next month" is the last day of the following month.
- "In N days" is the meeting date plus N days.
- "End of QN" is the last day of calendar quarter N (Mar 31, Jun 30, Sep 30, Dec 31) in the meeting's year, or the next year if that date is before the meeting date.
- A day of the month ("the 14th") or a month and day ("November 20") is the first such date on or after the meeting date.

## 6. Competitors

`competitors` is the full list of vendors the customer is currently evaluating against us, spelled as in the notes. It replaces the old list, so send the whole list. Vendors already on the opportunity stay on the list unless the customer says they ruled them out, even if they were not mentioned in this meeting (this also applies to won or lost deals). Remove vendors the customer says they ruled out. Do not add vendors the customer only used in the past or decided not to look at.

## 7. Tasks and next step

7.1 Create one task with `create_task` for each action a Brightwater person committed to in the meeting. Commitments by the customer are not tasks.
7.2 `owner_id` is the user ID (from `get_user_directory`) of the Brightwater person who will do the work, who may not have been on the call. Match on name and team.
7.3 `due_date` is the date agreed for that action (rules in 5.3, latest statement wins). If no date was agreed, use the meeting date plus 3 business days (Monday to Friday).
7.4 Set the opportunity's `next_step` to `YYYY-MM-DD: <action>` using the task with the earliest due date.

## 8. Contacts

Create a contact with `create_contact` for each new stakeholder named in the meeting with an email address who is not already in the CRM (check with `search_contacts`). Attach it to the opportunity's account. Fields: name, title, email, and phone only if a phone number was given.

## 9. Meeting note

Log exactly one note per meeting with `log_note` on the opportunity. Start it with the meeting ID (e.g. `MTG-4417`), followed by a two to five sentence summary of what was discussed and agreed.
