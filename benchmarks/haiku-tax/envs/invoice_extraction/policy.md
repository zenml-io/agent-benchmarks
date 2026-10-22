# Brindlewood Supply Co. Accounts Payable: incoming invoice procedure (AP-07)

The processing date for this queue is **Monday, 2026-03-16**. "Today" means this date.

You process documents from the AP inbox by document ID. Each document named in the request gets exactly one action: `submit_invoice`, `hold_invoice` or `reject_invoice`. An action is final once recorded, so finish your checks before you act. Do not act on documents that the request does not ask you to process.

## 1. Identify the vendor

1.1 Find the vendor by the tax ID printed on the invoice (VAT number, EIN, business number). Compare tax IDs ignoring spaces, dots and dashes. The vendor name alone is not enough: several vendors have near-identical names.

1.2 If no vendor master record has that tax ID, reject with `UNKNOWN_VENDOR`.

1.3 If the matching record has status `inactive`, reject with `VENDOR_INACTIVE`.

## 2. Checks, in this order (the first one that applies decides)

2.1 **Duplicate.** If the vendor's invoice history already contains the same invoice number, reject with `DUPLICATE`. Compare invoice numbers ignoring case, spaces and the characters `- / . #`.

2.2 **Currency.** We pay only in USD, EUR, GBP and CAD. An invoice in any other currency is rejected with `UNSUPPORTED_CURRENCY`.

2.3 **Purchase order required.** An invoice whose total (including tax) is 5,000.00 or more must reference a purchase order. If it does not, reject with `MISSING_PO`. A quote number, contract number or customer account number is not a PO.

2.4 **PO validity.** Any PO referenced on an invoice (at any amount) must exist, belong to the same vendor and have status `open`. Otherwise reject with `INVALID_PO`.

2.5 **Currency match.** If the invoice currency differs from the billing currency in the vendor master record, hold with `CURRENCY_MISMATCH`.

2.6 **PO balance.** The PO's remaining balance is `amount - invoiced_to_date`. If the invoice total exceeds the remaining balance, hold with `PO_EXCEEDED`. A total exactly equal to the remaining balance is fine.

2.7 If none of the above applies and you have no other concern about paying the invoice, submit it.

Use hold code `MANUAL_REVIEW` for any other concern that a person should resolve before the invoice is approved for payment, and explain the concern in `note`.

## 3. Reading documents

3.1 **Dates.** Vendors in the United States write numeric dates month first (MM/DD/YYYY). All other vendors write numeric dates day first (DD/MM/YYYY, DD.MM.YYYY). Use the vendor's country from the master record.

3.2 **Numbers.** Vendors in continental Europe (Germany, France, the Netherlands, Spain) write `1.234,56`. Others write `1,234.56`. Quantities follow the same convention.

3.3 **Invoice date** is the issue date (labelled Invoice Date, Date, Date of issue, Inv. Date, Dated or Issued). It is not the delivery, shipping or order date.

3.4 **Totals.** A document may show several totals. `subtotal` is the pre-tax amount (Subtotal, Net total, Total excl. VAT, Amount before tax). `tax` is the tax amount (0.00 if none). `total` is the amount payable for this invoice including tax. Ignore account balances and amounts relating to other invoices.

## 4. Submitting

4.1 Fields for `submit_invoice`:

- `vendor_id`: the master record ID (e.g. `V12345`).
- `invoice_number`: the vendor's invoice number as printed.
- `invoice_date`, `due_date`: `YYYY-MM-DD`.
- `currency`: ISO code (`USD`, `EUR`, `GBP`, `CAD`).
- `subtotal`, `tax`, `total`: numbers with two decimals, as printed on the document.
- `po_number`: in our format `PO-` followed by the ten digits (e.g. `PO-4500012345`); empty string if the invoice has no PO.
- `line_items`: every priced line above the subtotal, including freight, shipping or delivery lines, each with `description`, `quantity`, `unit_price` and `amount` as printed.

4.2 **Due date.** Compute it from the payment terms in the vendor master record, not the terms or due date printed on the invoice, counting from the invoice date:

- `Net N`: invoice date plus N calendar days.
- `2/10 Net 30`: invoice date plus 30 days (early-payment discounts are handled by Treasury).
- `EOM N`: the last day of the invoice date's calendar month plus N days.

## 5. Reason codes

- Reject: `UNKNOWN_VENDOR`, `VENDOR_INACTIVE`, `DUPLICATE`, `UNSUPPORTED_CURRENCY`, `MISSING_PO`, `INVALID_PO`.
- Hold: `CURRENCY_MISMATCH`, `PO_EXCEEDED`, `MANUAL_REVIEW`.

Reject only for the reject reasons above. Anything else that should stop an invoice from being paid is a hold.
