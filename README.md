# PV Deterministic Workbench

This repository now provides a deterministic Dash workbench for PV sizing and financial analysis. Phase 1 established the service layer and single-scenario MVP, phase 1.1 hardened validation and regression behavior, and phase 2A turns the app into a multi-scenario deterministic analysis tool.

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
- `components/`: reusable layout blocks for scenarios, assumptions, catalogs, validation, KPIs, and candidate exploration
- `services/`: Excel I/O, validation, deterministic runner, scenario-session state, exports, and result shaping

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

- Monte Carlo UI and stochastic scenario workflows
- background jobs and multi-user persistence
- scenario rejection-reason tracing for infeasible candidates
- broader economics-model redesign
- full removal of old matplotlib cross-check helpers

## Known technical debt

- Peak-ratio logic is still intentionally legacy-compatible. Representative-week aggregation and the current demand-seasonality interaction were not redesigned in this pass because changing them would alter the deterministic regression baseline.
- The browser session store now holds full deterministic scenario bundles and scan results. That is acceptable for phase 2A, but phase 2B may need more deliberate client-state sizing if scenario counts grow.
- The preserved `Resultados` artifacts still serve as the legacy regression oracle for the shipped workbook.
