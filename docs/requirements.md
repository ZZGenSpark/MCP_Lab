# IT Equipment Request Requirements

This document is the policy source for the IT equipment request system. Later mock data and tests must match the tables below. Dates are calendar dates (`YYYY-MM-DD`). Tests inject `today`.

## Request fields

| Field | Required | Rule |
| --- | --- | --- |
| `employee_id` | yes | Matches `^E\d{4}$` (four digits, uppercase `E`). Example: `E0001`. |
| `role` | yes | One of `standard`, `manager`, `contractor`, `intern`. Stored on the employee record. Compared after trimming whitespace and lowercasing. |
| `item` | yes | One catalog item, stored in lowercase. |
| `reason` | yes | Free text, or one of the escalation reason codes listed below. A reason used as an exception must be at least 10 characters, or be exactly one of those codes. |
| `request_date` | no | Calendar date the request is judged on. When omitted, use the injected `today`. |

The role used for a decision is the role on the employee record.

`check_request_eligibility(employee_id, item, reason)` takes the requester's own words as `reason`. The argument is optional. When it is omitted the reason is not judged, so the two-argument call from the lab spec still works. An empty `item` means the request names no item.

## Catalog

Requestable items:

| Item | Group |
| --- | --- |
| `monitor` | display |
| `laptop` | computer |
| `keyboard` | peripheral |
| `mouse` | peripheral |
| `dock` | peripheral |
| `headset` | peripheral |

`keyboard`, `mouse`, `dock`, and `headset` are peripherals. Any other named object, such as `standing desk`, is outside the catalog.

## Policy limits

Quantity is the most of that item a role may hold inside the refresh window. `0` means the role cannot receive the item. Refresh is the number of calendar years after `issued_on` before another unit is within policy.

Manager peripherals use the standard peripheral rule (quantity 1, refresh 2 years). Contractor and intern use that same peripheral rule. Manager rules that differ from standard are the monitor quantity (2) and the laptop refresh (2 years).

| Role | Item | Max quantity | Refresh (years) |
| --- | --- | --- | --- |
| standard | monitor | 1 | 3 |
| standard | laptop | 1 | 4 |
| standard | keyboard | 1 | 2 |
| standard | mouse | 1 | 2 |
| standard | dock | 1 | 2 |
| standard | headset | 1 | 2 |
| manager | monitor | 2 | 3 |
| manager | laptop | 1 | 2 |
| manager | keyboard | 1 | 2 |
| manager | mouse | 1 | 2 |
| manager | dock | 1 | 2 |
| manager | headset | 1 | 2 |
| contractor | monitor | 0 | — |
| contractor | laptop | 0 | — |
| contractor | keyboard | 1 | 2 |
| contractor | mouse | 1 | 2 |
| contractor | dock | 1 | 2 |
| contractor | headset | 1 | 2 |
| intern | monitor | 0 | — |
| intern | laptop | 0 | — |
| intern | keyboard | 1 | 2 |
| intern | mouse | 1 | 2 |
| intern | dock | 1 | 2 |
| intern | headset | 1 | 2 |

Probation length is **90 days** (`probation_days`). A near-boundary request is one that is still inside the refresh window with no more than **10%** of the window remaining (`near_boundary_fraction = 0.10`).

## Refresh window and quantity

For an item with `refresh_years = Y` and `issued_on = D`:

- The anniversary is `D` plus `Y` calendar years (same month and day).
- The request is **inside** the window when `today < anniversary`.
- The request is **outside** the window when `today >= anniversary`. The anniversary day itself is outside the window, so a refresh is allowed that day.
- The day before the anniversary is inside the window. The day after a past anniversary is outside it.

Remaining time for the near-boundary check is `(anniversary - today)` in days. The allowance is `round(Y * 365.25 * 0.10)` days. A 4-year laptop allowance is 146 days. A unit with 36 days left in a 4-year window is near the boundary.

Count toward the cap only units of the requested item whose `issued_on` is present and still inside the window. Units already outside the window are omitted from the count. If the count is below `max_quantity`, the request is inside the cap. If the count is at or above `max_quantity`, the cap is reached.

Worked monitor window for a standard employee, `today = 2026-01-01`, refresh 3 years:

| `issued_on` | Anniversary | Position | Counts toward the cap |
| --- | --- | --- | --- |
| 2023-01-02 | 2026-01-02 | one day inside | yes |
| 2023-01-01 | 2026-01-01 | anniversary (outside) | no |
| 2022-12-31 | 2025-12-31 | one day outside | no |

## Guiding principle

Deny when the records and the policy already answer no. A human has nothing left to weigh, and no review ticket is created.

Escalate when the employee and the item are real and a person could still approve. The facts are on file, and the policy does not settle the case. Escalation creates a review ticket.

Approve when the role may have the item, the quantity cap has room (or the held units are already outside the window), and probation has finished.

## Decision outcomes

### Approve

The item is in the role's limits with `max_quantity > 0`, the counted quantity is under that cap, and tenure is at least 90 days. No reason code. No ticket.

### Deny

A definite rejection. No ticket is created.

| Code | When it applies | What the reply must say |
| --- | --- | --- |
| `ROLE_NOT_ELIGIBLE` | The item's max quantity for that role is 0. Example: a contractor asks for a laptop and has no laptop on file. | The role cannot request that item. |
| `EMPLOYEE_NOT_FOUND` | The id fails `^E\d{4}$`, or it matches the pattern and is absent from the directory. There is no employee to review on behalf of. | Ask the requester to resubmit with a valid id. |
| `UNKNOWN_ITEM` | The request names an item that is not in the catalog. Example: `standing desk`. | List the six requestable items. |
| `LIMIT_REACHED` | The quantity cap is reached, the counted units are inside the window, and the reason is neither a hardware failure nor a near-boundary case. Example: a standard employee already holds the one allowed monitor and gives no failure reason. | State the role's quantity and refresh for that item. |

### Escalate

A person can reasonably say yes. Each case uses one reason code and creates one review ticket.

| Code | When it applies |
| --- | --- |
| `WITHIN_WINDOW_WITH_REASON` | The cap is reached and the window has not elapsed, and the reason is a hardware failure or the held unit is near the boundary. Example: the laptop policy is 4 years, the laptop on file is 3.9 years old, and the reason is that it is slow. |
| `TENURE_UNDER_90_DAYS` | The employee would otherwise be approved, and `tenure_days < 90`. The new hire needs manager sign-off. |
| `DATA_CONFLICT` | The record needed for this item cannot be trusted. Either a unit of the requested item has a missing or unparseable `issued_on`, or the employee already holds an item whose max quantity for their role is 0 (a contractor with a laptop on file). |
| `VAGUE_REQUEST` | The request does not name an item, or the reason is empty or shorter than 10 characters and is not an escalation reason code, so the request cannot be evaluated. A reason that is omitted from the tool call is not judged. When no item is named, the review ticket records the item as `unspecified`. |

Hardware failure is a case-insensitive substring match of the reason against this closed list: `broken`, `break`, `fail`, `failed`, `failure`, `damaged`, `damage`, `dead`, `not working`, `won't turn on`, `will not turn on`. A reason that only says the laptop is slow matches the near-boundary rule when the age qualifies, which is how the 3.9-year laptop escalates.

The match is a plain substring test on purpose, so `deadline` contains `dead`. A false match only sends a request that was inside its window and at its cap to a person. It never turns a denial into an approval. A hardware reason changes nothing on the approve path, the role denial, or the data-conflict path.

Tenure is `(today - start_date).days`. It is 0 on the start date. With `today = 2026-01-01`, a start date of `2025-10-04` is 89 days (still in probation) and `2025-10-03` is 90 days (probation complete).

## Decision table

Apply the first matching row.

| Order | Condition | Outcome | Reason code | Ticket |
| --- | --- | --- | --- | --- |
| 1 | Id is malformed or missing from the directory | Deny | `EMPLOYEE_NOT_FOUND` | no |
| 2 | No item is named, or the supplied reason is empty or under 10 characters and not an escalation code | Escalate | `VAGUE_REQUEST` | yes |
| 3 | The named item is outside the catalog | Deny | `UNKNOWN_ITEM` | no |
| 4 | A unit of that item has no usable `issued_on`, or the employee already holds an item the role's quantity sets to 0 | Escalate | `DATA_CONFLICT` | yes |
| 5 | The role's max quantity for the item is 0 | Deny | `ROLE_NOT_ELIGIBLE` | no |
| 6 | Cap is reached, window still open, and the reason is a hardware failure or the unit is near the boundary | Escalate | `WITHIN_WINDOW_WITH_REASON` | yes |
| 7 | Cap is reached, window still open, and no exception in row 6 applies | Deny | `LIMIT_REACHED` | no |
| 8 | Rows 1–7 do not match, and tenure is under 90 days | Escalate | `TENURE_UNDER_90_DAYS` | yes |
| 9 | Rows 1–8 do not match | Approve | — | no |

`check_request_eligibility` reports these same codes. `eligible` is `true` on the approve path, `false` on a deny path, and `"unclear"` on an escalate path. The final reply wording is chosen by the host.

## Mock data schema

Employee ids and item names follow the field rules above. `issued_on` and `start_date` are `YYYY-MM-DD` or, for `issued_on` only, JSON `null` when the date is unknown.

```json
{
  "employee_id": "E0001",
  "role": "standard",
  "start_date": "2020-01-15",
  "equipment": [
    {"item": "laptop", "issued_on": "2022-02-06"}
  ]
}
```

`equipment` may be an empty array. Policy data must carry every row of the policy table: `max_quantity`, and `refresh_years` when the quantity is greater than 0.

The directory must include at least these fixtures. Ages below use `today = 2026-01-01`.

| Id | Role | Start date | Equipment | What it supports |
| --- | --- | --- | --- | --- |
| `E1001` | standard | `2020-01-15` | none | First monitor can be approved. |
| `E1002` | contractor | `2021-06-01` | none | A laptop request is `ROLE_NOT_ELIGIBLE`. |
| `E1003` | standard | `2019-03-01` | laptop issued `2022-02-06` (36 days before the 4-year anniversary) | Near-boundary laptop is `WITHIN_WINDOW_WITH_REASON`. |
| `E1004` | standard | `2025-10-04` (89 days) | none | First monitor is `TENURE_UNDER_90_DAYS`. |
| `E1005` | contractor | `2021-06-01` | laptop issued `2024-01-01` | Laptop on file is `DATA_CONFLICT`. |
| `E1006` | standard | `2020-01-15` | monitor issued `2024-06-01`, still inside 3 years | A monitor request with no failure reason is `LIMIT_REACHED`. A reason that reports a failure, such as "My monitor is broken.", is `WITHIN_WINDOW_WITH_REASON`. |

An id such as `E9999` is valid in form and absent from the file, so a request with that id is `EMPLOYEE_NOT_FOUND`.

## Scenarios the policy must produce

Judged on `2026-01-01` against the fixtures above.

| Request | Outcome | Reason code |
| --- | --- | --- |
| `E1001` asks for a monitor. Reason: "I need a monitor for my desk." | Approve | — |
| `E1002` asks for a laptop. Reason: "I need a laptop for client work." | Deny | `ROLE_NOT_ELIGIBLE` |
| `E9999` asks for a monitor. Reason: "Please issue a monitor." | Deny | `EMPLOYEE_NOT_FOUND` |
| `E1001` asks for a standing desk. Reason: "I need a standing desk." | Deny | `UNKNOWN_ITEM` |
| `E1006` asks for a monitor. Reason: "I would like a second screen." | Deny | `LIMIT_REACHED` |
| `E1006` asks for a monitor. Reason: "My monitor is broken." | Escalate | `WITHIN_WINDOW_WITH_REASON` |
| `E1003` asks for a laptop. Reason: "My laptop is 4 years old and slow." | Escalate | `WITHIN_WINDOW_WITH_REASON` |
| `E1004` asks for a monitor. Reason: "I need a monitor for my desk." | Escalate | `TENURE_UNDER_90_DAYS` |
| `E1005` asks for a laptop. Reason: "My laptop no longer works." | Escalate | `DATA_CONFLICT` |
| `E1001` asks for equipment and names no item. Reason: "Help." | Escalate | `VAGUE_REQUEST` |
