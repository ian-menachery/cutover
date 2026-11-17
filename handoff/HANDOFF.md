# Hand-off to the portfolio site

Everything under `site/` drops into `~/projects/site` at the same paths:

| File | What it is |
|---|---|
| `site/lib/cutover.ts` | TypeScript port of the engine: defect composition, the eight checks, exception register, readiness |
| `site/lib/cutover.test.ts` | Vitest: 21 defect combinations must equal the Python reports exactly, plus DuckDB parsing cases |
| `site/data/cutover/demo.json` | clean demo migration (300 accounts, 779 legacy / 733 target policies), spec, register, nine defects as patches (225 KB, imported by the page) |
| `site/data/cutover/reference.json` | the Python engine's report for each of the 21 cases (614 KB, read by the test at runtime, never bundled) |
| `site/app/lab/cutover/page.tsx`, `cutover.tsx` | the demo: toggle defects, readiness banner, checks table, exception report |
| `site/app/work/cutover/page.mdx` | the case study |

Add to `lib/site.ts`:

```ts
// projects[], next to rentroll
  {
    slug: "cutover",
    title: "cutover",
    kind: "Data-migration tie-out kit",
    summary:
      "Checks a new system against the legacy system it replaced, row by row, and decides whether go-live can be signed off. It found 148 of 151 defects planted blind by an agent that never saw the checks.",
    repo: "https://github.com/ian-menachery/cutover",
    demo: "/lab/cutover",
  },

// demos[]
  { href: "/lab/cutover", title: "Migration tie-out", from: "cutover" },
```

To regenerate the data from the cutover repo: `py scripts/export_site.py`, then copy
`handoff/site/data/cutover/` again. The test file reads `reference.json` with
`readFileSync` so `tsc` never infers a type for it.

Check before merging: the case study's second paragraph names Sun Life and EY
work as motivation only. It says neither what the project is nor that the EY
work was client-facing. Keep or cut it to match the rest of the site.
