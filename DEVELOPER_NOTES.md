# Developer Notes — PVWorkbench

This document is for maintenance, debugging, packaging, and future handoff. It is not a user guide.

## Product direction

PVWorkbench is currently optimized for:

- local desktop usage
- workbook-driven deterministic design exploration
- project save/open workflows
- design comparison from a completed deterministic run
- fixed-design Monte Carlo risk analysis

It is not yet shaped for serious shared web deployment.

## Current product boundaries

The app now has explicit page ownership.

### `Resultados`

Owns the customer-facing deterministic output workflow:

- active scenario status
- deterministic run state
- viable candidate exploration
- selected-design deep dive
- unifilar / schematic result views

### `Supuestos`

Owns scenario setup:

- sidebar start actions (`Cargar ejemplo`, `Importar Excel`, project save/open)
- client-safe assumptions
- detailed demand editing under `Generales` / `Demanda`
- the internal access card that links to `Admin`

### `Admin`

Owns internal-only editing behind the local PIN gate:

- pricing-sensitive assumptions
- inverter and battery catalogs
- internal month, solar, and pricing tables

Important:

- detailed demand editing no longer belongs to `Admin`
- `Admin` should not mount hidden duplicate demand components
- if demand editing needs to change, do it in `Supuestos > Demanda`

### `Comparar`

Compares selected designs from the active scenario's latest deterministic scan.

### `Riesgo`

Runs Monte Carlo on one fixed design from a completed deterministic scenario.

### `Ayuda`

Provides the in-app product guide. The bundled `PVWorkbench_Guia_Rapida.html` is the companion quick-start document exposed through the local help route.

## Architecture summary

### 1. Browser state is intentionally thin

The browser-side session store keeps lightweight metadata only, for example:

- `session_id`
- active scenario id
- selected candidate keys
- comparison selections
- project binding / dirty state
- language / UI metadata
- revision counter

Heavy deterministic and stochastic objects remain server-side in process registries.

### 2. Scenario data lives server-side

Full scenario bundles and heavy results stay in server memory, keyed by session id and scenario id.

Implications:

- good for local responsiveness
- intentionally not ready for shared multi-worker deployment

### 3. Workspace drafts are server-side too

Unapplied edits are tracked as server-side workspace drafts per session and scenario.

This matters because:

- page interactions can stay responsive
- browser payloads stay small
- unapplied config/table edits survive navigation inside the same session

When debugging state issues, check both:

- committed scenario state
- pending workspace draft state

### 4. Deterministic scan cache

Deterministic scans are cached from effective deterministic inputs only.

The cache key includes normalized config/profile/catalog data plus a schema/version salt. It intentionally excludes:

- UI-only state
- project labels
- stochastic-only controls

### 5. Project persistence model

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

- CSV tables are the persisted source of truth
- reopening a project rebuilds bundles from those tables
- runtime blobs are not canonical inputs

### 6. Runtime and export paths

`services/runtime_paths.py` abstracts source versus packaged execution.

Important path behavior:

- source mode uses the repo root as the default runtime root
- project-bound sessions export into the active project workspace
- unbound sessions default to top-level `Resultados/` in source mode
- packaged Windows mode stores writable internal state under `%LOCALAPPDATA%/PVWorkbench/`
- packaged Windows mode publishes user-facing exports under `%USERPROFILE%/Documents/PVWorkbench Exports/`
- `MPLCONFIGDIR` is forced into a writable runtime cache path

### 7. Theming is centralized

The UI theme now lives primarily in `assets/app.css` through CSS variables in `:root`.

When updating colors, prefer using the existing token system rather than hardcoding values in components. Current important tokens include:

- primary / hover / soft primary
- active border
- text primary / secondary
- surface / panel colors
- state colors for success / warning / error / info

### 8. Help and docs surfaces are separate but should stay aligned

There are several documentation surfaces:

- `README.md` — repo/product overview
- `GUIA_USUARIO.md` — user-facing workflow guide
- `DEVELOPER_NOTES.md` — technical maintenance notes
- `pages/help.py` — in-app product guide
- `PVWorkbench_Guia_Rapida.html` — bundled quick-start HTML

Whenever workflow boundaries change, update all of them together.

## Current product capabilities

### Deterministic workflow

- load bundled example or import workbook
- edit assumptions and demand setup
- optionally edit internal catalogs/pricing tables in `Admin`
- run deterministic scan
- inspect viable candidates and discards
- select one design for deep-dive analysis
- export deterministic artifacts

### Comparison workflow

- build a shortlist of designs from the active scenario
- inspect grouped KPI comparison and charts
- export comparison workbook

### Risk workflow

- choose a deterministic scenario and design
- configure Monte Carlo settings
- inspect histogram / ECDF / percentile outputs
- export risk artifacts

## Recent implementation themes that matter for maintenance

### Workspace split

The old monolithic workbench workflow is now split into:

- `Resultados`
- `Supuestos`
- `Admin`
- `Comparar`
- `Riesgo`
- `Ayuda`

`pages/workbench.py` still exists as a compatibility/testing layer for shared helper functions and callbacks. It is not the main registered user page.

### Admin sanitization

A key UI/render bug came from `Admin` still depending on a hidden legacy demand subtree with duplicate IDs.

The healthy rule now is:

- no hidden duplicate demand editor in `Admin`
- no Admin callback should require those legacy IDs
- `Admin` owns only visible Admin components

### Local Admin PIN gate

The local PIN gate is intended as an internal-use barrier only.

Do not document or design it as real authentication:

- it is local
- it is session-scoped
- it is not a user-management system

### UI/UX theming cleanup

The navigation state, assumptions subtabs, empty-state CTAs, and table styling now depend on the centralized palette. Future UI work should extend those tokens instead of reintroducing scattered hardcoded colors.

## Important maintenance notes

### 1. Treat falsey config edits carefully

A recurring bug class in this app is legitimate falsey values being treated as missing.

When touching coercion/persistence:

- do not treat `False` as missing
- do not treat `0` as missing
- normalize only `None`, blank strings, and numeric `NaN` as missing where appropriate
- preserve empty-string semantics for text fields such as battery names

### 2. Respect page ownership

When adding a field or a table, decide first which page owns it.

Do not:

- duplicate the same editor on `Supuestos` and `Admin`
- keep hidden legacy components alive just to satisfy callbacks
- blur the boundary between client-safe setup and internal-only setup

### 3. Keep tests semantic, not brittle

Prefer tests that assert:

- stable ids and wrappers
- round-trip behavior
- selection synchronization invariants
- page ownership boundaries
- chart builder outputs and expected trace types

Avoid overfitting tests to incidental DOM nesting or cosmetic formatting.

### 4. Avoid plotting drift

Where the UI mirrors deterministic matplotlib exports, keep parity in:

- sign/color rules
- grouping/stacking semantics
- annotations and status badges
- month selection logic for typical-day views

### 5. Repo hygiene matters

The repo can accumulate noise from:

- `__MACOSX/`
- `.DS_Store`
- `__pycache__/`
- `Resultados/`
- `Resultados_rel/`
- project `inputs/` and `exports/`

Keep `.gitignore` strict enough to avoid shipping runtime/generated noise as source.

## Packaging notes

### Current spec status

`pv_app.spec` is suitable for the current one-folder Windows trial build.

It already bundles:

- desktop launcher entrypoint
- app assets
- page resources
- bundled workbook
- repo/user/help documents

### Suggested fire-test protocol

1. Build from a clean Windows environment.
2. Launch `dist/PVWorkbench/PVWorkbench.exe`.
3. Confirm browser auto-open works.
4. Confirm `Cargar ejemplo` and `Importar Excel` are visible in `Supuestos`.
5. Confirm the internal access card appears only in `Supuestos`.
6. Confirm deterministic scan completes and `Resultados` renders correctly.
7. Confirm `Admin` unlock/setup works and tables render without hidden legacy demand components.
8. Confirm save/open project works.
9. Confirm deterministic and risk exports go to the expected folders.
10. Ask the tester for friction feedback, not just bug feedback.

## Recommended next non-feature priorities

- validate packaged behavior on a clean Windows PC
- gather usability feedback from a real non-developer user
- do a small bug-fix pass from that feedback
- only then decide whether more features are warranted

## Suggested docs set

Keep these documents aligned:

- `README.md`
- `DEVELOPER_NOTES.md`
- `GUIA_USUARIO.md`
- `PVWorkbench_Guia_Rapida.html`

That split is better than forcing a single document to serve GitHub readers, developers, and end users at once.
