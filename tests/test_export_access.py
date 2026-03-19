from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import importlib
from pathlib import Path

from app import create_app
from services import bootstrap_client_session, commit_client_session
from services.export_access import ExportPublishResult, build_published_export_destination, open_export_folder, publish_export_artifacts
from services.io_excel import load_example_config
from services.runtime_paths import user_friendly_exports_root
import services.export_access as export_access
import services.runtime_paths as runtime_paths
from services.scenario_session import add_scenario, create_scenario_record, run_scenario_scan
from services.types import ScenarioSessionState


create_app()
risk_page = importlib.import_module("pages.risk")
workbench_page = importlib.import_module("pages.workbench")


def _fast_bundle():
    bundle = load_example_config()
    config = {
        **bundle.config,
        "years": 5,
        "modules_span_each_side": 4,
        "kWp_min": 12.0,
        "kWp_max": 18.0,
        "mc_n_simulations": 8,
    }
    return replace(bundle, config=config)


def _scanned_session_payload():
    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base Case", _fast_bundle()))
    state = run_scenario_scan(state, state.active_scenario_id)
    client = bootstrap_client_session("es")
    payload = commit_client_session(client, state).to_payload()
    return state, payload


def test_user_friendly_exports_root_is_disabled_in_source_mode() -> None:
    assert user_friendly_exports_root() is None


def test_user_friendly_exports_root_prefers_documents_in_frozen_mode(tmp_path, monkeypatch) -> None:
    documents_root = tmp_path / "Documents"
    monkeypatch.setattr(runtime_paths, "is_frozen_runtime", lambda: True)
    monkeypatch.setattr(runtime_paths, "_resolve_windows_documents_root", lambda: documents_root)

    root = runtime_paths.user_friendly_exports_root()

    assert root == (documents_root / "PVWorkbench Exports").resolve()
    assert root.exists()


def test_user_friendly_exports_root_falls_back_to_local_appdata(tmp_path, monkeypatch) -> None:
    fallback_root = tmp_path / "LocalAppData" / "PVWorkbench" / "Exports"
    monkeypatch.setattr(runtime_paths, "is_frozen_runtime", lambda: True)
    monkeypatch.setattr(runtime_paths, "_resolve_windows_documents_root", lambda: None)
    monkeypatch.setattr(runtime_paths, "_fallback_local_exports_root", lambda: fallback_root)

    root = runtime_paths.user_friendly_exports_root()

    assert root == fallback_root.resolve()
    assert root.exists()


def test_build_published_export_destination_uses_project_first_structure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(export_access, "user_friendly_exports_root", lambda: tmp_path)

    destination = build_published_export_destination(
        project_slug="demo-project",
        scenario_slug="Scenario 1",
        export_kind="deterministic",
        timestamp=datetime(2026, 3, 15, 9, 30, 0),
    )

    assert destination == (tmp_path / "demo-project" / "20260315_093000_deterministic" / "Scenario_1")


def test_publish_export_artifacts_copies_internal_tree_to_friendly_folder(tmp_path, monkeypatch) -> None:
    internal_root = tmp_path / "Resultados" / "Base"
    nested = internal_root / "autoconsumo_anual"
    nested.mkdir(parents=True, exist_ok=True)
    (internal_root / "chart.png").write_text("png", encoding="utf-8")
    (nested / "detalle.csv").write_text("csv", encoding="utf-8")
    friendly_root = tmp_path / "Documents" / "PVWorkbench Exports"
    monkeypatch.setattr(export_access, "user_friendly_exports_root", lambda: friendly_root)

    result = publish_export_artifacts(
        [internal_root / "chart.png", nested / "detalle.csv"],
        project_slug="demo-project",
        scenario_slug="Base Case",
        export_kind="deterministic",
        timestamp=datetime(2026, 3, 15, 10, 0, 0),
    )

    assert result.internal_root == internal_root.resolve()
    assert result.published_root == (friendly_root / "demo-project" / "20260315_100000_deterministic" / "Base_Case").resolve()
    assert (result.published_root / "chart.png").read_text(encoding="utf-8") == "png"
    assert (result.published_root / "autoconsumo_anual" / "detalle.csv").read_text(encoding="utf-8") == "csv"
    assert (internal_root / "chart.png").exists()


def test_publish_export_artifacts_returns_partial_success_when_copy_fails(tmp_path, monkeypatch) -> None:
    internal_root = tmp_path / "Resultados" / "Base"
    internal_root.mkdir(parents=True, exist_ok=True)
    chart = internal_root / "chart.png"
    chart.write_text("png", encoding="utf-8")
    monkeypatch.setattr(export_access, "user_friendly_exports_root", lambda: tmp_path / "Documents" / "PVWorkbench Exports")
    monkeypatch.setattr(export_access.shutil, "copytree", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("denied")))

    result = publish_export_artifacts(
        [chart],
        project_slug="demo-project",
        scenario_slug="Base Case",
        export_kind="deterministic",
        timestamp=datetime(2026, 3, 15, 10, 5, 0),
    )

    assert result.published_root is None
    assert result.display_root == internal_root.resolve()
    assert result.publish_error == "denied"


def test_open_export_folder_uses_exact_path(tmp_path, monkeypatch) -> None:
    opened: list[Path] = []
    folder = tmp_path / "published"
    folder.mkdir()
    monkeypatch.setattr(export_access, "_open_path_in_explorer", lambda path: opened.append(path))

    open_export_folder(str(folder))

    assert opened == [folder.resolve()]


def test_open_export_folder_raises_for_missing_path(tmp_path) -> None:
    missing = tmp_path / "missing"

    try:
        open_export_folder(str(missing))
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError for a missing export folder.")


def test_workbench_artifact_export_reports_published_path_and_store(tmp_path, monkeypatch) -> None:
    _, payload = _scanned_session_payload()
    internal_root = tmp_path / "internal" / "Base"
    friendly_root = tmp_path / "Documents" / "PVWorkbench Exports" / "demo" / "20260315_101000_deterministic" / "Base"
    monkeypatch.setattr(workbench_page, "export_deterministic_artifacts", lambda active, output_root: [internal_root / "chart.png"])
    monkeypatch.setattr(
        workbench_page,
        "publish_export_artifacts",
        lambda *args, **kwargs: ExportPublishResult(
            internal_root=internal_root,
            published_root=friendly_root,
            display_root=friendly_root,
            publish_error=None,
        ),
    )

    message, folder = workbench_page.export_active_artifacts(1, payload, "es")

    assert str(friendly_root.resolve()) in message
    assert folder == str(friendly_root.resolve())


def test_workbench_artifact_export_reports_partial_publish_failure(tmp_path, monkeypatch) -> None:
    _, payload = _scanned_session_payload()
    internal_root = tmp_path / "internal" / "Base"
    monkeypatch.setattr(workbench_page, "export_deterministic_artifacts", lambda active, output_root: [internal_root / "chart.png"])
    monkeypatch.setattr(
        workbench_page,
        "publish_export_artifacts",
        lambda *args, **kwargs: ExportPublishResult(
            internal_root=internal_root,
            published_root=None,
            display_root=internal_root,
            publish_error="denied",
        ),
    )

    message, folder = workbench_page.export_active_artifacts(1, payload, "es")

    assert str(internal_root.resolve()) in message
    assert "denied" in message
    assert folder == ""


def test_risk_artifact_export_reports_published_path_and_store(tmp_path, monkeypatch) -> None:
    state, payload = _scanned_session_payload()
    internal_root = tmp_path / "internal" / "Base" / "riesgo"
    friendly_root = tmp_path / "Documents" / "PVWorkbench Exports" / "demo" / "20260315_101500_risk" / "Base"
    monkeypatch.setattr(risk_page, "get_risk_result", lambda result_id: object())
    monkeypatch.setattr(risk_page, "export_risk_artifacts", lambda scenario, result, output_root: [internal_root / "histograma_vpn.png"])
    monkeypatch.setattr(
        risk_page,
        "publish_export_artifacts",
        lambda *args, **kwargs: ExportPublishResult(
            internal_root=internal_root,
            published_root=friendly_root,
            display_root=friendly_root,
            publish_error=None,
        ),
    )

    message, folder = risk_page.export_risk_result_artifacts(
        1,
        {"result_id": "risk-1", "scenario_id": state.active_scenario_id},
        payload,
        "es",
    )

    assert str(friendly_root.resolve()) in message
    assert folder == str(friendly_root.resolve())


def test_open_exports_callbacks_use_page_specific_latest_folder(tmp_path, monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(workbench_page, "open_export_folder", lambda path: opened.append(f"workbench:{path}"))
    monkeypatch.setattr(risk_page, "open_export_folder", lambda path: opened.append(f"risk:{path}"))

    workbench_message = workbench_page.open_workbench_exports_folder(1, str(tmp_path / "wb"), "es")
    risk_message = risk_page.open_risk_exports_folder(1, str(tmp_path / "risk"), "es")

    assert opened == [f"workbench:{tmp_path / 'wb'}", f"risk:{tmp_path / 'risk'}"]
    assert str(tmp_path / "wb") in workbench_message
    assert str(tmp_path / "risk") in risk_message
