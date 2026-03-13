# PV Sizing Dash MVP

This repository now has a first migration step from the original batch-style PV sizing workflow to a deterministic Dash application, plus a phase 1.1 hardening pass focused on trust, validation, and regression coverage.

## What is included in this step

- A deterministic service layer for:
  - loading the existing Excel workbook
  - validating normalized configuration
  - running the deterministic scan without Monte Carlo perturbation
  - shaping results for UI consumption
- A phase 1.1 hardening pass that:
  - removed arbitrary prime-module candidate exclusion
  - hardened workbook contract validation with friendlier structural errors
  - made CapEx inclusion semantics explicit and test-backed
  - added deterministic repeatability and legacy-regression tests
  - tightened candidate-table/detail selection consistency
- A single-page Dash app with:
  - Excel upload
  - bundled example loading
  - validation feedback
  - KPI summary cards
  - Plotly NPV vs kWp chart
  - Plotly monthly energy balance chart
  - Plotly cumulative cash flow chart
  - candidate results table with row selection
- A simplified legacy `main.py` entrypoint that still runs the deterministic scan from `PV_inputs.xlsx`

## Run the app

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open the local Dash URL printed in the terminal.

## Run the legacy CLI path

```bash
python main.py
```

This now loads `PV_inputs.xlsx`, validates it, runs the deterministic scan, and prints a concise summary.

## Tests

```bash
pytest
```

## Notes on the Excel contract

- The bundled `PV_inputs.xlsx` is treated as the source of truth for this migration step.
- The loader supports the current Spanish workbook names and table names:
  - `Config`
  - `Perfiles`
  - `Catalogos`
- The loader also normalizes known config mismatches such as:
  - `coupling` -> `bat_coupling`
  - `Sí` / `No` boolean values
  - profile mode strings like `Perfil Horario Relativo`
- Missing sheets, tables, or required columns now raise workbook-contract errors with actionable messages.
- Invalid booleans and enum-like config values are now surfaced as validation errors instead of silently defaulting.

## Costing semantics

- `pricing_mode="variable"` uses the variable `COP/kWp` table as the base project price.
- `pricing_mode="total"` uses `price_total_COP` as the base project price.
- `include_var_others=True` adds the separate variable “others” table on top of the base `kWp` table.
- `price_others_total` always adds fixed “other” project costs.
- `include_hw_in_price=True` adds inverter and selected battery prices on top of the base project price.
- `include_hw_in_price=False` assumes those hardware costs are already embedded in the base project price.

## Phase 1.1 notes

- Deterministic repeatability is now tested directly against the shipped workbook.
- Candidate ordering and selected-candidate resolution are now deterministic and aligned between the service layer and the Dash table.
- A legacy regression check now compares the current deterministic service path against the preserved batch artifacts in `Resultados`.
- Because prime module counts are no longer excluded, the current deterministic optimum can legitimately move relative to the preserved phase-1 batch artifacts even when the underlying candidate economics remain close.

## Known technical debt

- Peak-ratio logic remains intentionally legacy-compatible in phase 1.1. In particular, representative-week aggregation and the current demand-seasonality interaction are still simplified and were not redesigned in this pass because changing them risks altering feasibility and the preserved phase-1 regression baseline.
- The preserved `Resultados` artifacts were generated before deterministic and stochastic behavior were fully separated, so regression tolerances on NPV and payback remain wider than a pure deterministic baseline should require.
- Old matplotlib export helpers still exist for cross-checking and historical continuity, but the Dash UI does not depend on them.

## What remains for later

- Monte Carlo UI and stochastic scenario workflows
- report/export generation
- scenario comparison workflows
- cleanup/removal of old matplotlib export helpers once the new app fully replaces them
