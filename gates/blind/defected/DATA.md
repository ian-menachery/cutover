# A finished data migration: data dictionary

A fictional insurer moved its customer accounts and insurance policies from a
legacy policy-admin system to a new CRM. This folder holds the exports from both
sides after a **correct** migration, plus the signed-off mapping spec.

| File | What it is |
|---|---|
| `legacy_accounts.csv` | legacy customer accounts, key `CUST_NO` |
| `legacy_policies.csv` | legacy policies, key `POL_NO`; `CUST_NO` links to the account |
| `target_accounts.csv` | new-system accounts; `account_id` is the new id, `legacy_cust_no` the cross-reference to `CUST_NO` |
| `target_policies.csv` | new-system policies; `policy_id` new id, `legacy_pol_no` cross-reference to `POL_NO`, `account_id` links to the target account |
| `mapping.json` | the mapping spec (below) |
| `exceptions.csv` | accepted differences signed off by the business |

Row numbers are CSV line numbers: the header is line 1, the first record line 2.

## The mapping spec, in words

For each entity, every target field comes from one legacy field through one
transform:

- `text`: copied, surrounding whitespace trimmed.
- `date`: legacy `MM/DD/YYYY` becomes ISO `YYYY-MM-DD`.
- `money`: legacy text with thousands separators (`"1,234.50"`) becomes a plain
  decimal (`1234.50`).
- `map`: a coded value becomes its label through the value map
  (`PLAN_CD` `TL20` becomes `Term 20`). Only the listed codes and labels exist.
- `parent`: `target_policies.account_id` must be the `account_id` of the target
  account whose `legacy_cust_no` equals the legacy policy's `CUST_NO`.

Fields marked `required` must not be blank. `created_by` is a system column
outside the spec.

**Scope rule.** A legacy policy with `STATUS` = `LP` (lapsed) and a `LAPSE_DT`
before 2019-01-01 is deliberately not migrated. Every other legacy row should
be in the target exactly once, transformed as above. Accounts have no scope
rule: all of them migrate.

**Exception register.** `exceptions.csv` lists 4 pending policies the business
agreed to migrate by hand after go-live (ticket MIG-142). Their absence from
the target is accepted. Check code `R3` in that file means "legacy record with
no target row".

Control totals the business signs off: policy count, sum of `annual_premium`
and sum of `face_amount`, by `product` x `billing_mode`.
