# PV Sizing Dash MVP

This repository now has a first migration step from the original batch-style PV sizing workflow to a deterministic Dash application.

## What is included in this step

- A deterministic service layer for:
  - loading the existing Excel workbook
  - validating normalized configuration
  - running the deterministic scan without Monte Carlo perturbation
  - shaping results for UI consumption
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

## What remains for later

- Monte Carlo UI and stochastic scenario workflows
- report/export generation
- scenario comparison workflows
- cleanup/removal of old matplotlib export helpers once the new app fully replaces them
