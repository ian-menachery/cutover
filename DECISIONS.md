# Decisions

Newest last. Each entry: what was decided, why, and what it rules out.

## 1. Scope approved as written (2026-11-17)

Ian approved all four parts of `SCOPE.md` unchanged: the synthetic insurer
migration, the nine defects and eight checks, Gates 0-4 with their bars, and the
16-hour box with its out-of-scope list.

## 2. Engine: Python + DuckDB SQL (2026-11-17)

Each check is a SQL query over the loaded exports plus a thin Python wrapper.
Chosen over pure Python because SQL is the working language of the roles this
project is for, and because it makes the site's TypeScript port a genuinely
independent second implementation rather than a line-by-line transliteration.
The generator's ETL is plain Python, so the clean target is produced by
different code from the checker that verifies it.

## 3. Repo: public, MIT, created only after Gates 1-3 (2026-11-17)

Local until the gates have run, then `ian-menachery/cutover`, public, MIT. Data
is synthetic, so there is nothing to keep private. Until a remote exists,
`gate.py` skips its pushed-HEAD check and says so.

## 4. Demo: per-defect toggles (2026-11-17)

`/lab/cutover` ships the clean demo migration plus each defect as a patch; the
visitor switches defects on and off and the checks re-run in the browser. This
forces a design choice in the generator: every defect is a list of row-level
patch operations on clean data, composable in any subset, so Python and
TypeScript compose the same tables in the same order.

## 5. Gates 1 and 2 passed on the first run; that is weak evidence (2026-11-17)

Both gates passed without a single fix: 0 open findings on 20 clean seeds, and
19,869 of 19,869 injected instances found with no false positives on 20
defected seeds. That is the expected result when the same author writes the
generator and the checks: each check was written knowing exactly which defect
it was for. It shows the checks do what they were designed to do and that the
scope rule and deferrals do not raise false alarms. It does not show they catch
a defect nobody designed them for. That is Gate 3's question, and the reason it
is one-shot.

Before the gate run, scoring was tightened (SCOPE amendment): an R5 group
finding is credited only to instances that can move a control total. Without
it, the date-shift and lost-cross-reference defects were "caught by" R5 merely
because their rows sat in a group some other defect had broken.

## 6. Gate 3: pass, with one honest miss (2026-11-17)

A fresh subagent that never saw the checks designed 21 defect classes (151
instances) and 17 decoys against a clean seed-101 migration. The frozen checker
(`39cb853`, verified unchanged by `gates/gate3.py` before running) ran once:
20/21 classes, 148/151 instances, and nothing at all flagged outside the
answer key. It stayed silent on all the decoys (padded legacy names and states
the target correctly trimmed, lapse dates on either side of the scope cutoff).
It caught the defects written to slip past a narrow tie-out: offsetting
one-cent premium errors that leave control totals intact, premiums
cross-wired between neighbouring policies, a face amount parsed with the comma
as a decimal point, an issue date one day early, picklist values that are
valid but wrong for the row, a policy linked to a different account with the
same name, and re-keyed records.

The miss is B1, target account names that kept the legacy padding. The spec's
text transform says trim; the checker trims *both* sides before comparing, so
target-side whitespace can never show up as a difference. The same
normalisation is what kept the decoys silent, so the fix has to be
one-sided: normalise the legacy side, then compare the target's raw cell. Per
the pre-registered rule this is not patched and re-claimed. It goes to
BACKLOG, and a fixed checker would need a new blind set from a new author.

Limits of this evidence: the blind author is the same model family, the
defects were designed from the same data dictionary the checks implement, and
its answer key carries no control-total groups, so the 44 aggregate findings
(counts and totals) were not scored. They are consistent with the row-level
defects (out-of-scope Disability Income policies migrated, a partial load,
duplicate rows, a misparsed face amount), but that was read by eye, not counted.

## 7. Hours are wall-clock session time (2026-11-17)

The first log entry claimed "~5 hours to date"; that was an estimate, not a
measurement, and wrong. The session started at about 12:07 and the engine and
Gates 1-2 were committed by 12:33. Hours in the log are now wall-clock time
from the session, which for an agent session is far below the 16-hour box.
