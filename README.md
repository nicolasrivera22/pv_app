# PV Deterministic Workbench

This repository now provides a deterministic Dash workbench for PV sizing and financial analysis plus a first usable Monte Carlo risk page. Phase 1 established the service layer and single-scenario MVP, phase 1.1 hardened validation and regression behavior, phase 2A turned the app into a multi-scenario deterministic analysis tool, phase 2B.1 added the reproducible Monte Carlo service layer, and phase 2B.2 adds the Dash risk UI on top of that backend.

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

## Run the app

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open the local Dash URL shown in the terminal.

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
- `pages/workbench.py`: deterministic scenario load/edit/run/explore/export flow
- `pages/compare.py`: deterministic scenario comparison flow
- `pages/risk.py`: fixed-candidate Monte Carlo risk analysis flow
- `components/`: reusable layout blocks for scenarios, assumptions, catalogs, validation, KPIs, and candidate exploration
- `services/`: Excel I/O, validation, deterministic runner, scenario-session state, stochastic runner, server-side risk registry, exports, translation helper, and result shaping

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
- The browser session store now holds full deterministic scenario bundles and scan results. That is acceptable for phase 2A, but phase 2B may need more deliberate client-state sizing if scenario counts grow.
- The preserved `Resultados` artifacts still serve as the legacy regression oracle for the shipped workbook.
- The stochastic backend reuses the current monthly perturbation assumptions and representative-week simulator. It is suitable for phase 2B.1 risk summaries, but it does not yet model uncertainty in feasibility, hardware failures, or broader commercial assumptions.
- The risk registry in phase 2B.2 is intentionally single-process and in-memory. It is appropriate for local analysis, not for multi-worker deployment.
