# PVWorkbench

PVWorkbench is a Spanish-first local desktop and browser application for photovoltaic sizing, deterministic design exploration, project persistence, design comparison, and fixed-design economic risk analysis.

The app is built around a workbook-driven input contract (`PV_inputs.xlsx`) and is optimized for local execution, desktop packaging, and real user testing on Windows. It is not designed yet for serious multi-user web deployment.

## Current app map

The current product is intentionally split by page ownership:

- `Resultados` is the customer-facing deterministic results page. It shows the active scenario status, viable design exploration, selected-design KPIs, deep-dive charts, and the unifilar/schematic view.
- `Supuestos` is the setup page. It contains the scenario start actions in the sidebar (`Cargar ejemplo`, `Importar Excel`), the client-safe configuration fields, and the detailed demand editor under `Generales` / `Demanda`.
- `Admin` is internal-only. It is reached from the internal access card shown in `Supuestos`, protected by a local PIN gate, and owns pricing-sensitive assumptions, hardware catalogs, and internal month/solar/pricing tables.
- `Comparar` compares selected designs from the active scenario's latest deterministic scan.
- `Riesgo` runs Monte Carlo on one fixed deterministic design from a completed scenario.
- `Ayuda` is the in-app product guide, complemented by the bundled `PVWorkbench_Guia_Rapida.html`.

Important boundary:

- detailed demand editing now lives in `Supuestos > Demanda`
- `Admin` no longer mounts a hidden duplicate demand editor
- the internal access card is shown only in `Supuestos`, not in `Resultados`

## Current product status

The current iteration is suitable for a local Windows trial with a non-developer user, provided it is tested as a one-folder desktop build.

Already in place:

- thin browser session payloads with server-side scenario state
- session-scoped workspace drafts for unapplied edits
- deterministic cache keyed from effective deterministic inputs
- canonical project persistence using workbook-style CSV input tables
- explicit deterministic and risk exports
- Spanish-first UI with lightweight i18n support
- local PIN gate for internal Admin work
- centralized UI palette through CSS variables in `assets/app.css`
- desktop launcher with browser auto-open and health handshake
- PyInstaller one-folder packaging path

Still intentionally out of scope:

- multi-user deployment
- background orchestration
- installer / MSI packaging
- one-file executable packaging
- enterprise-grade authentication / authorization

## Main workflows

### 1. Start or reopen a workspace

From the sidebar in `Supuestos` you can:

- `Cargar ejemplo` to create a scenario from the bundled example
- `Importar Excel` to create a scenario from a valid workbook while keeping catalogs and profiles
- save a project
- save as a new project
- reopen an existing project

Each project stores canonical input tables per scenario plus project metadata.

In packaged Windows mode:

- writable internal app state lives under `%LOCALAPPDATA%/PVWorkbench/`
- projects live under `%LOCALAPPDATA%/PVWorkbench/projects/`
- internal unbound export staging lives under `%LOCALAPPDATA%/PVWorkbench/results/`
- published user-facing exports live under `%USERPROFILE%/Documents/PVWorkbench Exports/`

### 2. Configure assumptions

Use `Supuestos` for scenario setup.

- `Generales` contains client-safe assumptions and sizing controls
- `Demanda` contains the detailed demand workflow and its tables/charts
- the internal access card in `Supuestos` opens `Admin`

Use `Admin` only for internal work:

- pricing-sensitive assumptions
- inverter and battery catalogs
- internal month, solar, and pricing tables
- local PIN setup/unlock

### 3. Run deterministic exploration

The deterministic workflow evaluates design sizes under the active scenario and surfaces:

- viable NPV vs kWp exploration
- discard counters and discard markers when larger sizes were evaluated but filtered out
- candidate table
- selected-design KPI summary
- monthly balance
- cumulative discounted cash flow
- annual coverage, battery/load, energy destination, and typical-day views
- unifilar / schematic visualization

### 4. Compare shortlisted designs

`Comparar` works from the active scenario's latest deterministic scan.

You can:

- choose designs from the available list
- build a shortlist
- inspect summary tables and comparison charts
- export a comparison workbook

`Comparar` does not rerun the deterministic model by itself.

### 5. Run risk analysis

`Riesgo` works on one fixed design from a completed deterministic scenario.

You can:

- choose a completed scenario and a feasible design
- configure Monte Carlo uncertainty inputs
- inspect histograms, ECDFs, metadata, and percentiles
- export risk artifacts

### 6. Save, export, and consult the docs

- `Guardar proyecto` preserves the working scenarios in the app
- workbook exports produce workbook-style output files
- deterministic and risk export actions generate review/share packages
- `Ayuda` explains the current workflow inside the app
- `PVWorkbench_Guia_Rapida.html` is bundled for quick-start help in packaged mode

## Repository structure

- `app.py` — Dash shell, navigation, shared stores, and local help route
- `desktop_launcher.py` — local launcher used by the packaged desktop app
- `main.py` — legacy CLI path
- `pages/results.py` — deterministic results landing page
- `pages/assumptions.py` — setup workflow with `Generales` / `Demanda`
- `pages/admin.py` — internal Admin access shell
- `pages/compare.py` — deterministic design comparison
- `pages/risk.py` — Monte Carlo risk workflow
- `pages/help.py` — in-app product guide
- `pages/workbench.py` — compatibility layer for shared workbench callbacks/helpers
- `components/` — reusable UI blocks
- `services/` — state, I/O, persistence, runtime paths, cache, deterministic execution, risk execution, i18n, exports, and UI shaping
- `assets/app.css` — centralized theme tokens and shared UI styles
- `pv_product/` — core deterministic engineering and economic model
- `proyectos/` — saved local workspaces in source mode
- `Resultados/` — explicit internal export staging and legacy regression artifacts in source mode

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

The current supported target is a Windows one-folder build.

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

Send the entire `dist/PVWorkbench/` folder, ideally zipped without rearranging its contents. Do not send only `PVWorkbench.exe`.

## Packaging notes

The current `pv_app.spec` already bundles:

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

Useful focused suites during UI/doc-related work:

- `pytest -q tests/test_ui_refinement.py`
- `pytest -q tests/test_workspace_split.py`
- `pytest -q tests/test_admin_access.py`

## Recommended documents to ship with the executable

- `README.md` — repository-oriented overview and packaging notes
- `DEVELOPER_NOTES.md` — architecture and maintenance notes
- `GUIA_USUARIO.md` — user-facing workflow guide
- `PVWorkbench_Guia_Rapida.html` — bundled quick-start help, also exposed through the in-app help route

For an end user, the most relevant bundled documents are `GUIA_USUARIO.md` and `PVWorkbench_Guia_Rapida.html`.

## Known limitations

- optimized for local/single-user use
- in-process registries do not survive a full process restart
- the local Admin PIN gate is not real authentication
- packaged debugging is harder than source runs because the desktop executable hides the console by default
- the engineering/economic model is still conservative relative to a future broader redesign

## License / usage note

This repository is best treated as a local workbench/product in active development.
