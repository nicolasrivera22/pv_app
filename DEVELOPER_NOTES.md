# Developer Notes — PVWorkbench

This document is meant for future maintenance, debugging, packaging, and handoff. It is not a user guide.

## Product direction

PVWorkbench is currently in the best possible lane for:

- local desktop usage
- workbook-driven deterministic design exploration
- project save/open workflows
- side-by-side scenario comparison
- fixed-candidate Monte Carlo risk analysis

It is **not** yet shaped for serious multi-user web deployment.

## Architecture summary

### 1. Browser state is intentionally thin

The browser-side session store is lightweight and keeps only metadata such as:

- `session_id`
- active scenario id
- selected candidate keys
- comparison selections
- project binding / dirty state
- language / UI metadata
- revision counter

Heavy deterministic and stochastic objects are stored server-side in process registries.

### 2. Scenario data lives server-side

The app keeps full scenario bundles and heavy results in server memory keyed by session id and scenario id. This improves UI responsiveness and avoids browser storage bloat.

Important implication:

- the current architecture is excellent for local use
- it is not yet intended for shared multi-worker deployment

### 3. Deterministic scan cache

Deterministic scans are cached from effective deterministic inputs only.

The cache key intentionally includes a schema-version salt plus normalized config/profile/catalog data that materially affects the deterministic result.

The cache intentionally excludes:

- UI-only state
- project labels
- stochastic-only controls

### 4. Project persistence model

Saved projects live under:

```text
proyectos/<slug>/
```

Canonical inputs are stored as workbook-style CSV tables under:

```text
inputs/<scenario_id>/
```

`project.json` stores metadata only.

This means:

- the CSV tables are the source of truth
- project reopen rebuilds bundles from those tables
- runtime blobs are not treated as canonical persisted inputs

### 5. Runtime/export paths

The app supports both source and packaged execution through `services/runtime_paths.py`.

Important path behaviour:

- source mode uses the repo root as the default runtime root
- project-bound sessions export into `proyectos/<slug>/exports/Resultados/`
- unbound sessions default to top-level `Resultados/`
- packaged mode resolves a writable user/runtime root beside the executable
- `MPLCONFIGDIR` is forced into a writable runtime cache path to keep matplotlib safe in packaged and worker contexts

### 6. Multiprocessing

Only deterministic candidate evaluation uses multiprocessing.

The path is designed to be:

- spawn-safe
- Windows-friendly
- fallback-safe

The launcher and legacy entrypoints call `multiprocessing.freeze_support()`.

Current practical guidance:

- source execution is still the easiest debugging mode
- packaged multiprocessing is the right area to validate during the Windows fire test
- keep serial fallback intact even when enabling/using parallel execution in packaged mode

## Current product capabilities

### Deterministic workflow

- load workbook or bundled example
- edit assumptions/catalogues/profiles
- run deterministic scan
- inspect feasible candidates
- select a candidate for deep-dive analysis
- export scenario artifacts

### Comparison workflow

- compare multiple deterministic scenarios side by side
- inspect grouped KPI comparisons
- inspect overlaid NPV curves
- export comparison workbook

### Risk workflow

- choose deterministic scenario and candidate
- run Monte Carlo with explicit simulation count and seed
- inspect histogram / ECDF / percentile outputs
- export risk artifacts

## Recent important implementation work

### Foundation / stability work

- moved heavy scenario state out of browser payloads
- introduced session-scoped server-side registry
- added deterministic cache fingerprinting and reuse
- added project save/open with canonical CSV tables
- added explicit runtime/export path handling
- added spawn-safe deterministic executor and serial fallback

### Workbench UX / visualization work

- candidate selection and linked deterministic outputs
- selected-candidate deep-dive section
- unifilar/schematic visualization for selected candidate
- expanded deep-dive charting for selected design
- Spanish-first copy and lightweight translation layer

### Risk page work

- dedicated stochastic service layer
- compact server-side result handling
- separate Risk page with fixed-candidate Monte Carlo flow

## Important maintenance notes

### 1. Treat falsey config edits carefully

A real class of bugs in this app is: legitimate falsey values being treated as “missing”.

When working on config coercion or persistence:

- do not treat `False` as missing
- do not treat `0` as missing
- normalize only `None`, blank strings, and numeric `NaN` as missing where appropriate
- preserve empty string semantics for text config fields like battery names

### 2. Avoid duplicating plotting semantics

Where the UI mimics deterministic matplotlib exports, prefer shared prepared-series logic or at least very close parity.

Do not let Plotly and matplotlib drift too far in:

- sign/color rules
- grouping/stacking semantics
- annotations / badge logic
- month-selection logic for typical-day views

### 3. Keep tests semantic, not brittle

Prefer tests that assert:

- stable ids / wrappers
- semantic round-trip behaviour
- selection synchronization invariants
- view builder outputs and expected trace types

Avoid overfitting tests to incidental DOM nesting or cosmetic formatting.

### 4. Repo hygiene matters now

The repo can easily accumulate noise from:

- `__MACOSX/`
- `.DS_Store`
- `__pycache__/`
- `Resultados/`
- `Resultados_rel/`
- project `inputs/` and `exports/`

Keep `.gitignore` strict enough to avoid shipping runtime/generated noise as source.

## Packaging notes

### Current spec status

`pv_app.spec` is good enough for a first Windows trial build.

It already bundles the essentials:

- desktop launcher entrypoint
- app assets
- page resources
- bundled workbook

### What the current spec does not yet bundle automatically

If you want the trial package to include end-user documentation, developer notes, or a standalone HTML help file, add those files to `datas` in `pv_app.spec` or copy them into the `dist/PVWorkbench/` folder after build.

### Suggested first fire-test protocol

1. Build from a clean Windows environment.
2. Launch the packaged app from `dist/PVWorkbench/PVWorkbench.exe`.
3. Confirm browser auto-open works.
4. Confirm example workbook loads.
5. Confirm deterministic scan completes.
6. Confirm save/open project works.
7. Confirm export writes files into the expected folder.
8. Confirm risk page runs at least one small Monte Carlo job.
9. Ask the tester for friction feedback, not just bug feedback.

## Recommended next non-feature priorities

- packaging validation on a clean Windows PC
- usability feedback from a real non-developer user
- small bug-fix pass from that feedback
- only then decide whether more features are actually needed

## Suggested docs set

For the next milestone, keep these documents in the repo:

- `README_REPO.md`
- `DEVELOPER_NOTES.md`
- `GUIA_USUARIO.md`
- `PVWorkbench_Guia_Rapida.html`

That split is better than forcing one README to serve GitHub readers, developers, and end users simultaneously.
