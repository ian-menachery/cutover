# cutover

A data-migration tie-out kit. Give it the legacy system's export, the new
system's export and the signed-off mapping spec, and it says whether the
migration ties out, points at every row that does not, and says whether go-live
can be signed off.

Every check is deterministic SQL over the exports, with no model anywhere. The
data is synthetic: a seeded generator builds a fictional insurer's migration
and injects known defects, so detection can be scored.

**Live demo:** toggle the defects and watch the report change, on the
portfolio site at `/lab/cutover` (a TypeScript port of this engine, tested
against it).

## Results

Four gates, bars fixed in [`SCOPE.md`](SCOPE.md) before any code
([`DECISIONS.md`](DECISIONS.md) has the reasoning, `gates/results/` the raw output).

| Gate | Bar | Result |
|---|---|---|
| 1 Clean migrations raise nothing | 0 open findings, READY, on 20/20 seeds | **Pass.** 20/20 READY; only the 4 registered deferrals, waived |
| 2 Known defects found and located | 9/9 classes, 100% instance recall and precision, 20 seeds | **Pass.** 19,869/19,869 instances; 0 false positives in 21,679 findings; each defect caught by exactly the predicted checks |
| 3 Blind defects, one shot | ≥ 80% classes, ≥ 90% instances, 0 blockers outside the key | **Pass.** 20/21 classes, 148/151 instances, nothing flagged outside the key (17 decoys included) |
| 4 TypeScript port matches | 21/21 identical reports | **Pass.** 21/21 |

Gates 1 and 2 are graded against my own generator, which makes them weak
evidence: each check was written knowing which defect it was for. Gate 3 is the
real test. A separate agent that never saw the check code designed 21 defect
classes and 17 decoys from the data dictionary alone. The frozen checker
(`39cb853`) ran once against them. The blind set and its answer key are in
`gates/blind/`.

**The miss:** blind class B1, target account names that kept the legacy
padding (0/3). The checker trims both sides before comparing, so whitespace the
spec says should be gone can never appear as a difference. The same trimming
is what keeps padded *legacy* values (the decoys) silent, so the fix is
one-sided: trim the legacy side, compare the target's raw cell. It is in
[`BACKLOG.md`](BACKLOG.md), not patched, because a patched checker can only be
re-claimed on a new blind set.

What the blind round caught that a counts-and-totals tie-out would not:
offsetting one-cent premium errors, premiums cross-wired between neighbouring
policies, a face amount parsed with the comma as a decimal point, issue dates
one day early, picklist values that are valid but wrong for the row, a policy
moved to a different account with the same name, re-keyed records, and
out-of-scope lapsed policies that were migrated anyway.

Limits: the blind author is the same model family, not a human migration
analyst; it worked from the same data dictionary the checks implement; and its
44 count and control-total findings were checked by eye, not scored.

## The synthetic migration

A fictional insurer moves accounts and policies from a legacy policy-admin
export (upper case, `MM/DD/YYYY`, coded picklists, money with commas) to a new
CRM (ISO dates, labelled picklists, decimal money, new surrogate ids).

| Entity | Legacy file, key | Target file, cross-reference |
|---|---|---|
| accounts | `legacy_accounts.csv`, `CUST_NO` | `target_accounts.csv`, `legacy_cust_no` |
| policies | `legacy_policies.csv`, `POL_NO` | `target_policies.csv`, `legacy_pol_no` |

[`spec/mapping.json`](spec/mapping.json) is the mapping workbook as data: per
field a source, a target, a transform (text, date, money, value map, parent
lookup), a class (key, money, date, picklist, text) and a required flag; the
control-total groupings; and one scope rule: lapsed policies with a lapse date
before 2019-01-01 are not migrated. `exceptions.csv` is the register of
accepted differences. The base data defers 4 pending policies to manual
migration, so every run exercises the known-exception path.

The nine injected defects, each a patch on the clean data:

| ID | Defect | Caught by |
|---|---|---|
| D1 | dropped records (policies, and accounts with their policies) | R1, R3, R5 |
| D2 | accounts loaded twice under new ids | R1, R2 |
| D3 | semi-annual premiums doubled by a mapping bug | R5, R6 |
| D4 | legacy plan codes the value map lacks, loaded blank | R5, R7 |
| D5 | one load batch read issue dates as DD/MM | R6 |
| D6 | account names cut at 30 characters | R6 (warning) |
| D7 | blank legacy cross-reference on target policies | R2, R3 |
| D8 | UAT test accounts and policies left in the target | R1, R4, R5 |
| D9 | policies linked to the wrong account, or to none | R6, R8 |

## Checks

Each check is a SQL query over views the spec generates (`migration.py`) plus
a thin wrapper, returning `pass`, `fail` or `skip` and findings that name the
row: CSV line numbers in the legacy and target files (header is line 1), key,
field, legacy value, expected value, found value.

| ID | Check | Rule | Severity |
|---|---|---|---|
| R1 | `record_counts` | in-scope legacy rows, less registered deferrals, vs target rows | blocker |
| R2 | `key_integrity` | blank or duplicate keys | blocker (target), warning (legacy) |
| R3 | `source_orphans` | in-scope legacy keys with no target row | blocker |
| R4 | `target_orphans` | target rows matching no in-scope legacy key (separately: matching an out-of-scope one) | blocker |
| R5 | `control_totals` | count, premium, face amount by product x billing mode, to the cent | blocker |
| R6 | `field_diffs` | every mapped field of every matched pair, transformed legacy vs target | blocker; warning for text |
| R7 | `unmapped_values` | legacy codes the value map lacks; target values it does not allow, or blank where required | blocker |
| R8 | `referential_integrity` | policies whose `account_id` matches no target account | blocker |

Matching is on exact keys. A key matches when it appears exactly once on each
side; blank keys belong to R2 only, and duplicate keys to R2 only, since which
copy to compare is ambiguous. A value that does not parse is a difference,
never a silent match of two NULLs. A missing file or column makes the checks
that need it `skip`, and any skip blocks sign-off: unverified is not verified.

**Readiness:** `BLOCKED` if any open blocker or any skip; otherwise `READY`,
listing warnings to acknowledge, known exceptions (findings matched to the
register on check, entity and key) and stale register entries that matched
nothing.

## Use

```bash
pip install -e ".[dev]"
cutover generate out/demo --seed 1 --scale demo          # all nine defects
cutover generate out/clean --seed 1 --defects none
cutover check out/demo --json out/demo/report.json      # markdown report; exit 1 if BLOCKED
cutover score out/demo/report.json out/demo/answer_key.json
```

Without installing, set `PYTHONPATH=src` and use `py -m cutover.cli`.

```bash
py gate.py                 # Gate 0: ruff, pytest with 85% coverage floor on checks, clean tree
py gates/run_gates.py      # Gates 1 and 2, seeds 1-20 (about 30 s)
py scripts/export_site.py  # demo data + reference reports for the site port
cd handoff && npm install && npx vitest run   # Gate 4
```

## Layout

```
spec/mapping.json      the mapping spec
src/cutover/
  spec.py              spec loader
  migration.py         DuckDB load (all text) and the spec-generated views
  checks/r1..r8        one check per module
  runner.py            exception register, statuses, readiness
  report.py            markdown report
  score.py             scoring against an answer key
  synth/               legacy generator, correct ETL (plain Python), defects, scenarios
gates/                 gate runners, results, the recorded blind set
handoff/site/          TypeScript port, Vitest parity test, demo page, case study
```

## Out of scope

Real data of any kind; fuzzy matching or entity resolution; writing fixes back
to the target; any model call; Excel; a hosted service; more than two entities.

## License

MIT. See [`LICENSE`](LICENSE).
