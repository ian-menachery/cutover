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
