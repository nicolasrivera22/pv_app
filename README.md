# PVWorkbench

PVWorkbench is a Spanish-first local desktop and browser-based application for photovoltaic sizing, deterministic design exploration, and project-level financial analysis.

The app is built around a workbook-driven contract (`PV_inputs.xlsx`) and supports:

- deterministic scenario analysis and candidate exploration
- scenario editing from the UI
- project save/open workflows under `proyectos/`
- design comparison across deterministic scenarios
- Monte Carlo risk analysis for a selected deterministic candidate
- visual deep-dive outputs, including an interactive schematic/unifilar view
- explicit artifact export to `Resultados/`

This repository is currently optimized for **local use and desktop packaging**, not multi-user deployment.

## Current product status

The current iteration is already suitable for a real-world Windows trial with a non-developer user, provided it is tested as a local one-folder build.

What is already in place:

- server-side session/state architecture to keep browser payloads light
- deterministic cache keyed by effective deterministic inputs
- project persistence using canonical CSV input tables
- explicit deterministic and risk exports
- Spanish-first UI with lightweight i18n support
- desktop launcher with browser auto-open and health-check handshake
- PyInstaller one-folder packaging path

What is intentionally *not* in scope yet:

- multi-user web deployment
- background job orchestration
- installer / MSI packaging
- one-file executable packaging
- full enterprise-grade persistence or authentication

## Main workflows

### 1. Load or start a project

From the Workbench you can:

- load the bundled example workbook
- upload a workbook
- save a project under `proyectos/`
- reopen a previously saved project

Each saved project stores canonical input tables per scenario plus project metadata.

### 2. Edit a scenario

You can adjust:

- assumptions / configuration inputs
- inverter catalogue rows
- battery catalogue rows
- profile tables exposed through the workbook contract

After editing, apply changes and rerun the deterministic scan.

### 3. Run deterministic exploration

The Workbench computes feasible candidates and surfaces:

- NPV vs kWp exploration
- candidate table
- selected-candidate KPI summary
- monthly balance and cumulative discounted cash flow
- deep-dive visual outputs for the selected candidate

### 4. Compare scenarios

The Compare page lets you contrast completed deterministic scenarios side by side.

### 5. Run risk analysis

The Risk page runs Monte Carlo analysis for a selected deterministic candidate using the current scenario inputs.

## Repository structure

- `app.py` — Dash shell and shared stores
- `desktop_launcher.py` — local launcher used by the packaged desktop app
- `main.py` — legacy CLI path
- `pages/workbench.py` — deterministic scenario workflow
- `pages/compare.py` — deterministic comparison workflow
- `pages/risk.py` — Monte Carlo risk workflow
- `components/` — reusable UI blocks
- `services/` — I/O, persistence, runtime paths, caching, deterministic execution, risk execution, view shaping, i18n, and exports
- `pv_product/` — core deterministic engineering/financial model
- `proyectos/` — saved local workspaces
- `Resultados/` — explicit exports and legacy regression artifacts

## Run from source

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python desktop_launcher.py
```

For direct Dash development:

```bash
python app.py
```

## Windows packaging

The current supported packaging target is a **Windows one-folder build**.

Compile it with:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt -r requirements-desktop.txt
pyinstaller --clean --noconfirm pv_app.spec
```

The packaged output is created under:

```text
dist/PVWorkbench/
```

## What to send after compiling

Send the entire `dist/PVWorkbench/` folder, ideally zipped without rearranging its contents.

Do **not** send only `PVWorkbench.exe`. The one-folder build depends on the bundled support files that live next to the executable.

## Packaging notes

The current `pv_app.spec` is already suitable for a first Windows trial build because it bundles:

- `assets/`
- `pages/`
- `PV_inputs.xlsx`
- the desktop launcher entrypoint
- `README.md`
- `DEVELOPER_NOTES.md`
- `GUIA_USUARIO.md`
- `PVWorkbench_Guia_Rapida.html`

## Testing

```bash
pytest
```

## Recommended documents to ship with the executable

For the Windows trial, do not rely on the repository README alone.

Recommended shipping set:

- `README.md` — repository-oriented overview and packaging notes
- `DEVELOPER_NOTES.md` — internal architecture and maintenance notes
- `GUIA_USUARIO.md` — short user-facing guide for the person testing the `.exe`
- `PVWorkbench_Guia_Rapida.html` — quick-start help document bundled in the distribution and also exposed inside the app Help page

For an end user, the most relevant bundled documents are `GUIA_USUARIO.md` and `PVWorkbench_Guia_Rapida.html`.

## Known limitations

- optimized for local/single-user use
- in-process registries do not survive full process restart
- packaged debugging is harder than source runs because the desktop executable hides the console by default
- the economics/model assumptions are still intentionally conservative relative to a broader future redesign

## License / usage note

This repository is currently best treated as a local product/workbench in active development.
