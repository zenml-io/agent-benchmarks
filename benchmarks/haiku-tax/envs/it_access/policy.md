# Quillmont Systems IT Access Request Procedure (ITP-7)

This procedure governs how the IT service desk handles access tickets. A ticket may ask for several things. Treat each (beneficiary, resource) pair as one **item**, decide every item, then close the ticket once. These rules set the minimum checks and the maximum access allowed; use judgment where the facts call for less.

## 1. Terms

1. **Requester**: the person who filed the ticket (`requester_id` in `get_ticket`).
2. **Beneficiary**: the person who would receive the access (the requester, unless the ticket asks on behalf of someone else).
3. **Current manager**: the `manager_id` in the beneficiary's directory record (`get_employee`). A `previous_manager_id` is not the manager.
4. **Need level**: `read` = view, look up, read, check, review or run read-only reports. `write` = create, update, edit, upload or make changes. `admin` = manage user permissions or change configuration. Order: read < write < admin; a role "covers" a need if its `access_level` is equal or higher.

## 2. Checks, in this order, for each item

1. **Account status.** If the beneficiary's `status` is not `active`, deny with `INACTIVE_ACCOUNT`.
2. **Who may ask.** The requester must be the beneficiary or the beneficiary's current manager. Otherwise deny with `NOT_AUTHORIZED`.
3. **Role selection.**
   - If the request names a role, that role may be granted. If no role with exactly that name exists on the resource, deny with `ROLE_NOT_FOUND`; do not substitute a similar name. If the named role is `deprecated`, use its `replaced_by` role instead. Never grant a deprecated role.
   - If no role is named, check the role catalog (`get_role_catalog`) for the beneficiary's department. If it has an entry for the beneficiary's exact title on that resource and its `default_role` covers the need, that role may be granted.
   - Otherwise use the non-deprecated role with the lowest access level that covers the need.
4. **Contractors.** A beneficiary with `employment_type` = `contractor` may not hold an `admin`-level role. Deny with `CONTRACTOR_ADMIN`.
5. **Expiry date** (see section 4).
6. **Existing access.** If the beneficiary already holds the selected role on that resource (`get_current_access`) with an `expiry_date` on or after the computed expiry date, take no action on the item.
7. **Approvals** (see section 3). If a valid approver has rejected, deny with `APPROVAL_REJECTED`. If a required approval is missing, call `request_approval` for each missing one and do not grant or deny the item.
8. Otherwise **grant** with `grant_access`.

## 3. Approvals

| Resource tier | Approvals required |
|---|---|
| T1 | none |
| T2 | manager |
| T3 | manager and resource owner |

Any `admin`-level role also requires resource-owner approval, whatever the tier.

Only approvals recorded on the ticket (`get_approvals`) count; a manager filing the ticket is not an approval. A recorded approval counts only if:

- it is for the same `resource_id` as the item;
- its `approval_type` matches (`manager` or `resource_owner`);
- a manager approval comes from the beneficiary's current manager;
- a resource-owner approval comes from the resource's `owner_id` or one of its `owner_delegates`.

Request a missing manager approval from the beneficiary's current manager, and a missing resource-owner approval from the resource's `owner_id` (not a delegate).

## 4. Expiry dates

All dates are `YYYY-MM-DD`. Count from the ticket's `opened_on` date, not today's date.

1. If the request states a period ("for N days", "for N weeks") or an end date ("until YYYY-MM-DD"), the wanted date is `opened_on` + that period, or that end date.
2. Otherwise the wanted date is `opened_on` + the default: 90 days for employees, 30 days for contractors.
3. The expiry date is the wanted date, but never later than `opened_on` + the maximum: T1 365 days, T2 180 days, T3 30 days. For contractors the maximum is never more than 90 days.

## 5. Tools and codes

- `grant_access(employee_id, resource_id, role, expiry_date)`
- `deny_request(ticket_id, employee_id, resource_id, reason_code)`, reason codes: `INACTIVE_ACCOUNT`, `NOT_AUTHORIZED`, `ROLE_NOT_FOUND`, `CONTRACTOR_ADMIN`, `APPROVAL_REJECTED`.
- `request_approval(ticket_id, approver_id, resource_id)`
- `close_ticket(ticket_id, resolution_code)`: call exactly once, after all items. Use `PENDING_APPROVAL` if any item is waiting for approval; otherwise `GRANTED` if any item was granted; otherwise `DENIED` if any item was denied; otherwise `NO_ACTION_NEEDED`.

Use employee and resource IDs, never names, in write calls. People and resources can have near-identical names: confirm the department and the exact resource before acting.
