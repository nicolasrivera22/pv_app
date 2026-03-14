# PV Deterministic Workbench

This repository now provides a deterministic Dash workbench for PV sizing and financial analysis plus a usable Monte Carlo risk page. Phase 1 established the service layer and single-scenario MVP, phase 1.1 hardened validation and regression behavior, phase 2A turned the app into a multi-scenario deterministic analysis tool, phase 2B.1 added the reproducible Monte Carlo service layer, phase 2B.2 added the Dash risk UI, and phase 2B.3 refined the app into a Spanish-first, workbook-driven product.

## What phase 2C adds

- The Workbench now includes an interactive unifilar-style schematic for the currently selected deterministic candidate.
- The diagram is built from a dedicated service-layer helper in `services/schematic.py`, not from callback-local logic.
- It shows, at minimum:
  - inferred PV string groups / MPPT blocks
  - inverter
  - optional battery
  - house / load
  - grid
- Stringing is inferred without any prime-number exclusion rule:
  - the service first searches for an exact equal-length layout that uses all modules and respects the existing inverter/string constraints
  - if no exact equal-length layout can be derived from the stored candidate data, the app falls back to a clearly labeled representative layout
- The diagram is Spanish-first and explicitly labeled as schematic / representative:
  - it is meant to explain the selected design visually
  - it is not a certified installation drawing
- Schematic export is intentionally deferred:
  - the existing artifact export flow remains unchanged
  - this phase focuses on the interactive Workbench visualization only

## What phase 2B.3 adds

- Spanish is now the default UI language.
- The lightweight translation layer now covers the shell, workbench, comparison, validation, exports, and risk-page copy.
- The assumptions editor is now driven by metadata from the workbook `Config` table:
  - fields keep workbook order
  - fields are grouped by `Grupo`
  - help text comes from `Descripción`, with small curated overrides where needed
  - units from `Unidad` are shown in the editor
  - a curated basic view is shown first, with advanced parameters still available
- The app now surfaces more workbook flexibility from `Perfiles`:
  - `Month_Demand_Profile`
  - `SUN_HSP_PROFILE`
  - `Precios_kWp_relativos`
  - `Precios_kWp_relativos_Otros`
  - mode-aware demand-profile editing for:
    - `Demand_Profile`
    - `Demand_Profile_General`
    - `Demand_Profile_Weights`
- UI-facing metric aliases, formatting, and tooltips are centralized in `services/ui_schema.py`.
- Deterministic runs now show explicit loading feedback in the workbench.
- The risk payback histogram highlights the central 80% finite-payback band (`P10-P90`).
- Explicit artifact export is available again:
  - deterministic artifacts can be written into `Resultados/`
  - risk artifacts can be written into `Resultados/`
  - exports are additive only; the app never wipes output folders automatically

## What phase 2A adds

- Session-scoped scenario management:
  - load scenarios from Excel uploads
  - load the bundled example
  - duplicate, rename, delete, and switch active scenarios
  - keep multiple deterministic scenarios available in one browser session
- In-app deterministic editing:
  - editable assumptions panel for key design and pricing controls
  - editable inverter and battery catalogs with row add/delete support
  - friendly validation messages carried through the service layer
- Better deterministic exploration:
  - selectable feasible-candidate table with filtering and sorting
  - richer Plotly NPV hover data and linked candidate selection
  - KPI cards, monthly energy balance, and cumulative cash flow for the selected candidate
- Scenario comparison:
  - compare completed deterministic scenarios side by side
  - grouped KPI chart across scenarios
  - overlaid NPV-vs-kWp curves
- Explicit deterministic export:
  - scenario workbook export from the workbench
  - comparison workbook export from the comparison page

## What phase 2B.1 adds

- A dedicated stochastic service layer:
  - `run_monte_carlo(...)`
  - `summarize_monte_carlo(...)`
  - `prepare_risk_views(...)`
- Reproducible fixed-candidate Monte Carlo with explicit `seed=0` default behavior.
- Structured stochastic result objects with:
  - metadata
  - compact distribution summaries
  - risk probabilities
  - histogram / ECDF / percentile-table view data
  - optional raw per-draw samples
- Monte Carlo perturbation of the existing supported uncertainty inputs only:
  - `mc_PR_std`
  - `mc_buy_std`
  - `mc_sell_std`
  - `mc_demand_std`
- Payback semantics for stochastic runs:
  - `payback_years` stays `NaN` when payback is not reached within the horizon
  - payback percentiles are computed over finite cases only
  - `probability_payback_within_horizon` is reported separately
- A documented soft warning threshold for large runs:
  - `MONTE_CARLO_WARNING_THRESHOLD = 5000`
- large runs are allowed, but the result carries a warning

## What phase 2B.2 adds

- A dedicated `Risk` page in the Dash app for fixed-candidate Monte Carlo analysis.
- Risk-page controls for:
  - selecting a completed deterministic scenario
  - selecting a feasible deterministic candidate
  - choosing simulation count
  - setting an explicit seed with default `0`
  - optionally retaining raw samples in server memory only
- Interactive Monte Carlo outputs built from compact stochastic summaries:
  - summary KPI cards
  - NPV histogram and ECDF
  - payback histogram and ECDF
  - percentile summary table
  - run metadata and uncertainty-knob display
- Lightweight server-side result handling:
  - Monte Carlo results are kept in an in-process registry keyed by a lightweight `result_id`
  - browser state stores only compact metadata and the `result_id`
  - raw samples never go into browser-side `dcc.Store`
- Lightweight bilingual UI support:
  - English and Spanish translation dictionaries via `services/i18n.py`
  - shared shell labels plus all new Risk page labels/messages use the translation helper

## Spanish-first UI notes

- The app now defaults to Spanish (`es`) in the shell language selector.
- Translation fallback order is:
  - selected language
  - Spanish
  - English
  - raw key
- This keeps new UI coverage maintainable without introducing a heavy i18n framework.

## Risk UI notes

- Phase 2B.2 still supports `fixed_candidate` mode only. `optimal_per_draw` is not exposed in the UI yet.
- The selected seed is visible in the UI and the same seed with the same inputs reproduces the same Monte Carlo result.
- Payback values that are not reached within the project horizon remain `NaN`.
  - Payback percentiles are computed over finite cases only.
  - `probability_payback_within_horizon` is shown separately.
- The server-side Monte Carlo registry is intentionally simple for this phase:
  - it is in-process only
  - it does not survive app restarts
  - it is not shared across multiple workers
  - it is bounded and prunes older results
- The payback histogram highlight band represents the central 80% finite-payback range:
  - left bound = `P10`
  - right bound = `P90`

## Run the app

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python desktop_launcher.py
```

This launcher starts the local server and opens the default browser automatically when the app is ready.

For development/debugging, the original Dash entrypoint remains available:

```bash
python app.py
```

## Desktop packaging

Phase 10C adds a Windows-first local packaging path using PyInstaller and a dedicated desktop launcher.

- Supported build target for this phase:
  - one-folder distribution
  - bundled `assets/`
  - bundled `pages/`
  - bundled `PV_inputs.xlsx`
  - browser auto-open via `desktop_launcher.py`
- Runtime path behavior:
  - source mode writes explicit exports into `Resultados/` under the repo root
  - packaged mode writes explicit exports into `Resultados/` beside the executable
  - the bundled example workbook is loaded from the packaged resource directory
- The app still creates `Resultados/` on demand; no precreated skeleton output folder is required.

### Build the executable

On Windows, from the repository root:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt -r requirements-desktop.txt
pyinstaller --clean --noconfirm pv_app.spec
```

The packaged app is produced under `dist/PVWorkbench/`.

### Browser auto-open

- The executable starts the local Dash server on `127.0.0.1`.
- It prefers port `8050` and moves to the next free local port if needed.
- The default browser opens only after the launcher confirms that `/healthz` is reachable.

### Current limitations

- This phase is Windows-first and one-folder only.
- It does not yet add an installer, a one-file bundle, or tray/menu integration.
- The packaged executable runs without a console window by default, so source runs remain the easier debugging path.

## Run the legacy CLI path

```bash
python main.py
```

This still loads `PV_inputs.xlsx`, validates it, runs the deterministic scan, and prints a concise summary.

## Tests

```bash
pytest
```

## App structure

- `app.py`: Dash shell, navigation, shared stores
- `desktop_launcher.py`: local desktop-style launcher with browser auto-open
- `pages/workbench.py`: deterministic scenario load/edit/run/explore/export flow
- `pages/compare.py`: deterministic design comparison flow for the active scan
- `pages/risk.py`: fixed-candidate Monte Carlo risk analysis flow
- `components/`: reusable layout blocks for scenarios, assumptions, catalogs, validation, KPIs, and candidate exploration
- `services/`: Excel I/O, config metadata extraction, validation, deterministic runner, scenario-session state, stochastic runner, server-side risk registry, display schema, exports, translation helper, and result shaping

## Workbook-driven editing notes

- The assumptions board now reads the workbook-facing `Config` metadata directly and no longer depends on a narrow hardcoded field list.
- The UI schema still applies curated overrides for:
  - widget type
  - display label
  - help text when the workbook description is too technical
  - basic vs advanced visibility
- Most workbook controls are now surfaced either as direct config fields or as editable `Perfiles` tables.
- Controls that remain intentionally out of the UI are limited to fields that are currently:
  - internal/legacy implementation knobs not meant for normal operators
  - redundant with already exposed controls
  - unsafe to present casually without deeper workflow design
- At the moment, the main intentionally deferred controls are the legacy low-level island/SoC iteration knobs that are present in `DEFAULT_CONFIG` but not part of the shipped workbook contract.

## Explicit artifact export

- Workbook export remains available from the app as before.
- In addition, explicit artifact export now writes charts/files into `Resultados/`:
  - deterministic export writes scenario-specific PNG/CSV/TXT artifacts
  - risk export writes scenario-specific risk PNG/CSV/TXT artifacts
- The export path is service-driven and opt-in.
- The app does not delete or wipe existing contents inside `Resultados/`.

## Stochastic service notes

- Phase 2B.1 supports `fixed_candidate` mode only.
- The stochastic path starts from a validated deterministic scenario and a resolved deterministic candidate.
- Deterministic scans remain deterministic; Monte Carlo perturbations are applied only inside the stochastic runner.
- By default, stochastic runs return compact summaries and chart-ready tables, not full raw sample payloads.
- If you need per-draw samples for debugging or offline analysis, use `return_samples=True`.

## Notes on the Excel contract

- The bundled `PV_inputs.xlsx` remains the authoritative workbook contract for the deterministic app.
- The loader supports the current Spanish workbook names and table names:
  - `Config`
  - `Perfiles`
  - `Catalogos`
- The loader normalizes known mismatches such as:
  - `coupling` -> `bat_coupling`
  - `Sí` / `No` boolean values
  - profile mode strings like `Perfil Horario Relativo`
- Missing sheets, tables, or required columns raise workbook-contract errors with actionable messages.
- Invalid booleans and enum-like config values surface as validation errors instead of silently defaulting.

## Costing semantics

- `pricing_mode="variable"` uses the variable `COP/kWp` table as the base project price.
- `pricing_mode="total"` uses `price_total_COP` as the base project price.
- `include_var_others=True` adds the separate variable “others” table on top of the base `kWp` table.
- `price_others_total` always adds fixed “other” project costs.
- `include_hw_in_price=True` adds inverter and selected battery prices on top of the base project price.
- `include_hw_in_price=False` assumes those hardware costs are already embedded in the base project price.

## What remains deferred

- `optimal_per_draw` stochastic support in the backend and UI
- richer stochastic comparison workflows across scenarios and candidates
- background jobs and multi-user persistence
- scenario rejection-reason tracing for infeasible candidates
- broader economics-model redesign
- full removal of old matplotlib cross-check helpers
- full-app localization beyond the current lightweight English/Spanish foundation

## Known technical debt

- Peak-ratio logic is still intentionally legacy-compatible. Representative-week aggregation and the current demand-seasonality interaction were not redesigned in this pass because changing them would alter the deterministic regression baseline.
- The browser-side scenario store is in-memory only. That avoids storage quota issues, but scenarios do not survive a full browser refresh.
- The preserved `Resultados` artifacts still serve as the legacy regression oracle for the shipped workbook.
- The stochastic backend reuses the current monthly perturbation assumptions and representative-week simulator. It is suitable for phase 2B.1 risk summaries, but it does not yet model uncertainty in feasibility, hardware failures, or broader commercial assumptions.
- The risk registry in phase 2B.2 is intentionally single-process and in-memory. It is appropriate for local analysis, not for multi-worker deployment.
- Display labels and help text are now centralized, but a few older deterministic/risk internals still carry technical column names beneath the UI layer. Those should keep shrinking rather than being copied into callbacks.
