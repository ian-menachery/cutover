# SCOPE: cutover

Committed before any implementation. Amendments go in the dated table at the
bottom, never as a silent edit. Gates and bars below are fixed before code.

**Package:** `cutover` · **Started:** 2026-11-17 · **Time box:** 16 hours of
work; hard stop at 20.

**One-line purpose:** Given a legacy-system export, the new system's export, and
the signed-off mapping spec, say whether the migration ties out, point at every
row that does not, and say whether go-live can be signed off.

---

## The question

After a data migration, the new system has to be shown to hold what the old one
held, transformed the way the mapping spec says. That proof is usually manual:
spreadsheets of counts, a few spot checks, and a meeting. Can a deterministic
kit do it end to end (counts, control totals, field-level diffs, orphans,
duplicates, unmapped values), localize every problem to a row, and stay silent
on a clean migration?

Because the data is synthetic, every injected defect is known, so detection can
be scored. A test I grade against my own generator is weak evidence, so Gate 3
uses defects designed blind by someone who never saw the checks.

## The synthetic migration

A fictional insurer moves from a legacy policy-admin export to a new CRM. All
data comes from a seeded generator; no real people, companies, or products.

| Entity | Legacy file and key | Target file and cross-reference |
|---|---|---|
| accounts | `legacy_accounts.csv`, `CUST_NO` | `target_accounts.csv`, `legacy_cust_no` |
| policies | `legacy_policies.csv`, `POL_NO` | `target_policies.csv`, `legacy_pol_no` |

Legacy style: upper-case text, `MM/DD/YYYY` dates, coded picklists (`PLAN_CD`
`TL10`, `MODE` `S`), money as text with commas. Target style: ISO dates, labelled
picklists (`Term 10`, `Semi-annual`), decimal money, new surrogate ids.

The **mapping spec** (`spec/mapping.json`) is the signed-off mapping workbook as
data: source field → target field, transform (text, date with format, money,
value map, parent lookup), field class (key, money, date, picklist, text),
required flag, the control-total groupings, and one **scope rule**: lapsed
policies with a lapse date before 2019-01-01 are deliberately not migrated. A
checker that ignores the scope rule false-FAILs every clean migration; that is
the trap the clean gate exists to catch.

An **exception register** (`exceptions.csv`: check, entity, key, reason,
ticket) lists differences the business has already accepted. The base data has
4 pending policies deferred to manual migration (ticket `MIG-142`), so every
run, clean or not, exercises the known-exception path.

Scale: gate runs use 1,500 accounts and about 4,000 policies per seed; the
portfolio demo uses 300 accounts and about 800.

## Injected defects (the answer key)

Each defect is a patch on the clean data, recorded instance by instance as
(entity, key or target row, field). Row-level defects use disjoint rows.
Field-level defects may share a row only on different fields. The "caught by"
column is the prediction, registered now.

| ID | Defect | What happens | Caught by |
|---|---|---|---|
| D1 | dropped records | ~12 in-scope policies and 2 accounts (with their policies) never load | R1, R3, R5 |
| D2 | duplicated accounts | 5 accounts load twice under new ids | R1, R2 |
| D3 | doubled amounts | mapping bug: every semi-annual policy's annual premium is ×2 | R5, R6 |
| D4 | unmapped picklist values | legacy rows carry 2 plan codes the value map lacks; they load blank | R7, R5 |
| D5 | date-format shift | one load batch read `issue_date` as DD/MM: swapped where day ≤ 12, blank where day > 12 | R6 |
| D6 | truncated text | account names longer than 30 characters are cut at 30 | R6 (warning) |
| D7 | lost cross-reference | 8 target policies arrive with a blank `legacy_pol_no` | R2, R3 |
| D8 | extra target records | 3 test accounts and 5 test policies left in the target | R1, R4, R5 |
| D9 | broken parent links | 6 policies point at the wrong account (3) or at no account (3) | R6, R8 |

An instance is recorded only if the patch actually changed something (a DD/MM
swap of 03/03 is not a defect).

## Checks

Every check is a pure function `(Migration, Spec) -> CheckResult` with status
`pass`, `fail` or `skip`, and findings with structured refs: side, entity, CSV
row number, key, field, source value, target value. A check never raises on
missing input; it returns `skip` with a reason, and a skip is shown as
prominently as a fail.

Matching rule: a key is matched when it appears exactly once on each side.
Rows with a blank key belong to R2 only. Duplicate keys belong to R2 and are
excluded from R3, R4 and R6, because which copy to compare is ambiguous.

| ID | Check | Rule | Severity |
|---|---|---|---|
| R1 | `record_counts` | in-scope source rows (minus registered deferrals) vs target rows, per entity | blocker |
| R2 | `key_integrity` | blank or duplicate keys, both sides | blocker (target), warning (source) |
| R3 | `source_orphans` | in-scope source keys with no target row: dropped records | blocker |
| R4 | `target_orphans` | target rows whose cross-reference matches no source key | blocker |
| R5 | `control_totals` | count, premium and face amount by product × billing mode, expected vs target, exact to the cent | blocker |
| R6 | `field_diffs` | each mapped field of each matched pair: transformed source vs target | blocker for key, money, date, picklist; warning for text |
| R7 | `unmapped_values` | source picklist values the value map lacks; target picklist values outside the allowed list or blank where required | blocker |
| R8 | `referential_integrity` | target policies whose `account_id` matches no target account | blocker |

R6 does not compare a field whose source value is unmapped; R7 owns it.

**Exception register.** A finding matching a register entry (check, entity,
key) is a known exception, not a blocker. A register entry that matches nothing
is reported as a stale exception (warning).

**Readiness.** `BLOCKED` if any unwaived blocker exists or any check skipped;
otherwise `READY`, listing warnings to acknowledge and known exceptions.

## Engine

Python with DuckDB SQL: files load as text and parse explicitly, the spec
generates the "expected target" view, and each check is a SQL query plus a thin
wrapper. The generator's ETL is separate Python, so the clean target is built by
different code than the checker that verifies it. The site demo is a TypeScript
port, a second independent implementation, held to the same answers (Gate 4).

## Gates (bars fixed now)

**Gate 0, quality.** `py gate.py` exits zero: ruff lint and format, pytest,
coverage ≥ 85% on `cutover.checks`, clean working tree, HEAD pushed if a remote
exists.

**Gate 1, clean migrations raise nothing.** Seeds 1-20, clean scenario, gate
scale. Pass: zero unwaived findings of any severity in 20/20; all 4 registered
deferrals matched as known exceptions; no skips; readiness `READY` in 20/20.
Fail action: stop. A false alarm on clean data means a check's basis is wrong;
fix the basis, log the cause in DECISIONS, re-run all 20.

**Gate 2, known defects found and located.** Seeds 1-20, all nine defects.
Pass, all of:
- class recall 9/9 in 20/20 seeds;
- instance recall 100% pooled: every instance referenced by an unwaived finding
  naming its row, and its field for field-level defects;
- precision 100%: every row ref ties to an instance; every group ref
  (control totals) or count ref contains one;
- readiness `BLOCKED` in 20/20, with D6 listed under warnings, not blockers.

Fail action: report the miss with its cause before changing anything. Fixes are
allowed (the generator and checker are both mine), but each one is logged and
the gate re-runs on all 20 seeds.

**Gate 3, blind defects. One shot.** A fresh subagent that has never seen the
check code gets the data format, the mapping spec and a clean dataset (seed 101,
gate scale). It designs at least 6 defects of its own that a careful migration
reviewer should catch (the target disagrees with what the spec implies, or a
record is missing, extra or duplicated), applies them with its own script, and
writes a sealed answer key. I record the checker's commit hash, then run it once.
Pass: class recall ≥ 80%, instance recall ≥ 90%, and zero blocker findings on
rows outside its answer key.
Fail action: publish the result as it is. No patch-and-reclaim. A fixed checker
can only be re-tested on a new blind set from a new subagent, and both results
are reported. Known limit: the blind author is the same model family, not a
human reviewer.

**Gate 4, two implementations agree.** The TypeScript port reproduces the
Python reports exactly (statuses, findings, refs, totals to the cent) on the
demo dataset for clean, each defect alone, all nine, and 10 random
combinations: 21 cases. Pass: 21/21 identical. Fail action: fix the port; it is
a port, not a claim.

**Blanket stop.** At 16 hours, ship what exists. Past 20, stop regardless.

## Deliverables

- The engine, CLI (`cutover check ...`), generator and scorer.
- Gate results in `gates/` and `DECISIONS.md`.
- README with real numbers, written early as the spec and corrected at the end.
- Portfolio hand-off in `handoff/site/`: `lib/cutover.ts` + Vitest test against
  Python reference JSON, `data/cutover/`, `app/lab/cutover/page.tsx` (toggle
  defects, see the report and readiness change), `app/work/cutover/page.mdx`,
  and the `lib/site.ts` entries. The Phase 3 portfolio session merges them.

## Out of scope

- Any real data, and any real company, system or product name.
- Fuzzy matching or entity resolution: exact keys only.
- Fixing the target: the kit reports, it never writes back.
- Any model call anywhere. Every check is deterministic.
- Excel input or output, a hosted service, Streamlit, auth.
- More than two entities, more than ~10,000 rows per entity, performance work.
- Scheduling, CI integration, connectors to real systems.
- Claims about Sun Life or EY work. The story may cite them as motivation; the
  project is not that work, and EY work is never described as client-facing.

## Anti-polish rules

- Every session ends with one line in the log below.
- No commit that only renames, reformats or restructures working code.
- Improvements to things that work go in `BACKLOG.md`, untouched this time box.

---

## Log

| Date | Hours to date | What changed | Next |
|---|---|---|---|
| 2026-11-17 | ~0.5 | Repo created, SCOPE drafted. | Ian's approval, then spec + generator. |
| 2026-11-17 | ~5 | SCOPE approved. Spec, DuckDB loader and views, R1-R8, runner with exception register and readiness, generator (legacy data, independent Python ETL, nine defects as patches), scorer, 32 tests at 99% coverage on checks. Gates 1 and 2 pass on first run. | Gate 3 blind round, then the TypeScript port. |

## Gate results

| Gate | Date | Result | Decision |
|---|---|---|---|
| 0 quality | | | |
| 1 clean | 2026-11-17 | pass | 20/20 clean seeds READY: 0 open findings, all 4 deferrals matched as known exceptions, 0 stale, 0 skips. Proceed. |
| 2 known defects | 2026-11-17 | pass | 9/9 classes in 20/20 seeds; 19,869/19,869 instances (100%); 0 false positives in 21,679 open findings; BLOCKED 20/20 with D6 under warnings only; every defect caught by exactly the predicted checks. Self-graded, so weak evidence alone: Gate 3 decides. |
| 3 blind defects | | | |
| 4 port parity | | | |

## Amendments

| Date | What changed and why |
|---|---|
| 2026-11-17 | R5's expected side also excludes registered deferrals. A deferred policy is a reconciling item; without this every run, clean or not, fails R5 in the deferred policies' groups, the same false alarm R1's rule already prevents. Written before the first gate run. |
| 2026-11-17 | R4 compares against in-scope legacy keys and names a target row that matches an out-of-scope legacy row as `out_of_scope` (a scope violation) rather than letting it pass as "matched". R6 also counts an unparseable legacy value as a difference, so two NULLs never silently match. Both written before the first gate run. |
| 2026-11-17 | Gate 2 scoring, stated exactly: a control-total finding counts as a true positive only if an instance that can move a total (a row on one side only, or a change to a summed or grouped field) touches its group; a count finding when its entity has an instance. Stricter than the bar as first written. Fixed before the gate run. |
