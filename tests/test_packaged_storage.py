from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import shutil

import pytest

import services.runtime_paths as runtime_paths
from services import (
    add_scenario,
    configure_runtime_environment,
    create_scenario_record,
    internal_app_root,
    internal_results_root,
    list_projects,
    open_project,
    project_exports_root,
    projects_root,
    runtime_cache_root,
    save_project,
)
from services.desktop_runtime import desktop_runtime_dir
from services.io_excel import load_example_config
from services.types import ScenarioSessionState


def _fast_bundle():
    bundle = load_example_config()
    config = {
        **bundle.config,
        "years": 5,
        "modules_span_each_side": 4,
        "kWp_min": 12.0,
        "kWp_max": 18.0,
    }
    return replace(bundle, config=config)


def _patch_frozen_runtime(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    resource_dir = tmp_path / "bundle"
    legacy_dir = tmp_path / "dist"
    local_appdata = tmp_path / "LocalAppData"
    resource_dir.mkdir()
    legacy_dir.mkdir()
    local_appdata.mkdir()
    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "_MEIPASS", str(resource_dir), raising=False)
    monkeypatch.setattr(runtime_paths.sys, "executable", str(legacy_dir / "PVWorkbench.exe"), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setattr(runtime_paths, "_MIGRATION_ATTEMPTED", False)
    return resource_dir, legacy_dir, local_appdata


def _write_legacy_project(monkeypatch, legacy_dir: Path, *, project_name: str, slug: str):
    with monkeypatch.context() as ctx:
        ctx.setattr(runtime_paths.sys, "frozen", False, raising=False)
        ctx.setattr(runtime_paths, "user_root", lambda: legacy_dir)
        state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
        return save_project(state, project_name=project_name, slug=slug, language="es")


def test_packaged_storage_roots_resolve_under_local_appdata(tmp_path, monkeypatch) -> None:
    _, legacy_dir, local_appdata = _patch_frozen_runtime(monkeypatch, tmp_path)
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)

    assert runtime_paths.legacy_packaged_root() == legacy_dir.resolve()
    assert internal_app_root() == (local_appdata / "PVWorkbench").resolve()
    assert projects_root() == (local_appdata / "PVWorkbench" / "projects").resolve()
    assert runtime_cache_root() == (local_appdata / "PVWorkbench" / "cache").resolve()
    assert desktop_runtime_dir() == (local_appdata / "PVWorkbench" / "runtime").resolve()
    assert internal_results_root() == (local_appdata / "PVWorkbench" / "results").resolve()

    configure_runtime_environment()

    assert Path(os.environ["MPLCONFIGDIR"]) == (local_appdata / "PVWorkbench" / "cache" / "matplotlib").resolve()


def test_packaged_project_save_and_open_use_new_internal_projects_root(tmp_path, monkeypatch) -> None:
    _, _, local_appdata = _patch_frozen_runtime(monkeypatch, tmp_path)

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    saved = save_project(state, project_name="Proyecto Demo", language="es")

    project_base = local_appdata / "PVWorkbench" / "projects" / saved.project_slug
    assert project_base.exists()
    assert (project_base / "project.json").exists()
    assert (project_base / "inputs" / saved.active_scenario_id / "Config.csv").exists()
    assert project_exports_root(saved.project_slug) == (project_base / "exports" / "Resultados").resolve()

    reopened = open_project(saved.project_slug)

    assert reopened.project_slug == saved.project_slug
    assert reopened.project_name == "Proyecto Demo"


def test_open_project_uses_legacy_fallback_only_when_new_root_lacks_project(tmp_path, monkeypatch) -> None:
    _, legacy_dir, local_appdata = _patch_frozen_runtime(monkeypatch, tmp_path)
    legacy_saved = _write_legacy_project(monkeypatch, legacy_dir, project_name="Proyecto Legacy", slug="legacy-demo")

    marker_path = local_appdata / "PVWorkbench" / "migration" / "storage_layout_v1.json"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        json.dumps({"schema_version": 1, "attempted_at": "2026-03-15T00:00:00+00:00", "legacy_source_path": str(legacy_dir), "status": "partial", "categories": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_paths, "_MIGRATION_ATTEMPTED", False)

    reopened = open_project(legacy_saved.project_slug)
    assert reopened.project_name == "Proyecto Legacy"

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    current_saved = save_project(state, project_name="Proyecto Nuevo", slug=legacy_saved.project_slug, language="es")

    preferred = open_project(current_saved.project_slug)
    assert preferred.project_name == "Proyecto Nuevo"


def test_list_projects_prefers_new_root_and_avoids_legacy_duplicates(tmp_path, monkeypatch) -> None:
    _, legacy_dir, _ = _patch_frozen_runtime(monkeypatch, tmp_path)
    _write_legacy_project(monkeypatch, legacy_dir, project_name="Proyecto Legacy", slug="demo")

    state = add_scenario(ScenarioSessionState.empty(), create_scenario_record("Base", _fast_bundle()))
    save_project(state, project_name="Proyecto Nuevo", slug="demo", language="es")

    manifests = list_projects()

    assert len(manifests) == 1
    assert manifests[0].name == "Proyecto Nuevo"


def test_migration_is_best_effort_and_writes_versioned_marker(tmp_path, monkeypatch) -> None:
    _, legacy_dir, local_appdata = _patch_frozen_runtime(monkeypatch, tmp_path)
    legacy_projects = legacy_dir / "proyectos" / "demo"
    legacy_projects.mkdir(parents=True, exist_ok=True)
    (legacy_projects / "project.json").write_text("{}", encoding="utf-8")
    legacy_cache = legacy_dir / ".pv_runtime_cache" / "matplotlib"
    legacy_cache.mkdir(parents=True, exist_ok=True)
    (legacy_cache / "fontlist-v330.json").write_text("cache", encoding="utf-8")

    original_copy2 = shutil.copy2

    def flaky_copy(source, destination, *args, **kwargs):
        if str(source).endswith("fontlist-v330.json"):
            raise OSError("denied")
        return original_copy2(source, destination, *args, **kwargs)

    monkeypatch.setattr(runtime_paths.shutil, "copy2", flaky_copy)

    root = internal_app_root()
    marker_path = local_appdata / "PVWorkbench" / "migration" / "storage_layout_v1.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))

    assert root == (local_appdata / "PVWorkbench").resolve()
    assert (local_appdata / "PVWorkbench" / "projects" / "demo" / "project.json").exists()
    assert marker["schema_version"] == 1
    assert marker["legacy_source_path"] == str(legacy_dir.resolve())
    assert marker["status"] == "partial"
    assert marker["categories"]["projects"]["copied"] >= 1
    assert marker["categories"]["matplotlib_cache"]["status"] == "partial"


def test_migration_is_idempotent_and_does_not_repeat_after_marker_exists(tmp_path, monkeypatch) -> None:
    _, legacy_dir, local_appdata = _patch_frozen_runtime(monkeypatch, tmp_path)
    marker_path = local_appdata / "PVWorkbench" / "migration" / "storage_layout_v1.json"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(
        json.dumps({"schema_version": 1, "attempted_at": "2026-03-15T00:00:00+00:00", "legacy_source_path": str(legacy_dir), "status": "complete", "categories": {}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_paths, "_MIGRATION_ATTEMPTED", False)
    monkeypatch.setattr(runtime_paths, "_copy_tree_conservative", lambda *args, **kwargs: pytest.fail("migration should not recopy after marker"))

    payload = runtime_paths.migrate_legacy_packaged_storage()

    assert payload["status"] == "complete"


def test_top_level_legacy_resultados_is_not_migrated(tmp_path, monkeypatch) -> None:
    _, legacy_dir, local_appdata = _patch_frozen_runtime(monkeypatch, tmp_path)
    legacy_results = legacy_dir / "Resultados"
    legacy_results.mkdir(parents=True, exist_ok=True)
    (legacy_results / "keep.txt").write_text("legacy export", encoding="utf-8")

    runtime_paths.migrate_legacy_packaged_storage()

    assert not (local_appdata / "PVWorkbench" / "results" / "keep.txt").exists()
    marker = json.loads((local_appdata / "PVWorkbench" / "migration" / "storage_layout_v1.json").read_text(encoding="utf-8"))
    assert marker["ignored_legacy_outputs"] == ["Resultados", "Resultados_rel"]
