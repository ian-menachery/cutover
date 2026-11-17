# Backlog

Not worked on during the current time box. Add a line, keep moving.

| Date | Idea | Why it is not now |
|---|---|---|
| 2026-11-17 | Compare the target's raw text cell, not a trimmed copy, so target-side padding (Gate 3 miss B1) is a difference. Keep trimming the legacy side, which is what keeps padded legacy values (the decoys) silent. | Gate 3 is one-shot: a patched checker can only be re-claimed against a new blind set from a new author, and both results reported. |
| 2026-11-17 | R7's message prints Python's `None` when an in-scope legacy row has a blank key and an unmapped code; R6 prints `expected legacy None` when the legacy parent key is blank. Use "blank" like the other messages. | Cosmetic; the TypeScript port reproduces it exactly so the parity test stays exact. Change both together. |
| 2026-11-17 | The TypeScript port rejects exponent money (`1e3`), which DuckDB's DECIMAL cast accepts. | No demo data uses it; noted in `lib/cutover.ts`. |
| 2026-11-17 | Score control-total findings in Gate 3-style blind keys by recomputing group membership from the data instead of needing groups in the key. | The 44 aggregate findings in Gate 3 were checked by eye only. |
