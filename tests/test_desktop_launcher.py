from __future__ import annotations

import shutil
from pathlib import Path

from app import create_app
import desktop_launcher
from services import io_excel
from services.runtime_paths import assets_dir, bundled_workbook_path, default_results_root, pages_dir, resource_root, user_root


ROOT = Path(__file__).resolve().parent.parent


def test_runtime_paths_resolve_to_repo_root_in_source_mode() -> None:
    assert resource_root() == ROOT
    assert user_root() == ROOT
    assert assets_dir() == ROOT / "assets"
    assert pages_dir() == ROOT / "pages"
    assert bundled_workbook_path() == ROOT / "PV_inputs.xlsx"


def test_runtime_paths_use_frozen_resource_and_user_roots(tmp_path, monkeypatch) -> None:
    resource_dir = tmp_path / "bundle"
    user_dir = tmp_path / "dist"
    resource_dir.mkdir()
    user_dir.mkdir()

    monkeypatch.setattr("services.runtime_paths.sys.frozen", True, raising=False)
    monkeypatch.setattr("services.runtime_paths.sys._MEIPASS", str(resource_dir), raising=False)
    monkeypatch.setattr("services.runtime_paths.sys.executable", str(user_dir / "PVWorkbench.exe"), raising=False)

    assert resource_root() == resource_dir.resolve()
    assert user_root() == user_dir.resolve()
    assert bundled_workbook_path() == (resource_dir / "PV_inputs.xlsx").resolve()
    assert default_results_root() == (user_dir / "Resultados").resolve()
    assert default_results_root().exists()


def test_load_example_config_uses_runtime_bundled_workbook_path(tmp_path, monkeypatch) -> None:
    workbook = tmp_path / "sample.xlsx"
    shutil.copyfile(ROOT / "PV_inputs.xlsx", workbook)
    monkeypatch.setattr(io_excel, "bundled_workbook_path", lambda: workbook)

    bundle = io_excel.load_example_config()

    assert bundle.source_name == "sample.xlsx"


def test_create_app_uses_explicit_runtime_asset_and_pages_folders_and_healthz() -> None:
    app = create_app()
    client = app.server.test_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert Path(app.config.assets_folder) == assets_dir()
    assert Path(app.pages_folder) == pages_dir()


def test_create_local_server_skips_busy_ports(monkeypatch) -> None:
    attempted_ports: list[int] = []
    fake_server = object()

    def fake_make_server(host, port, app, threaded=True):
        attempted_ports.append(port)
        if len(attempted_ports) == 1:
            raise OSError("busy")
        return fake_server

    monkeypatch.setattr(desktop_launcher, "make_server", fake_make_server)
    server, port = desktop_launcher.create_local_server(object(), start_port=8050, max_attempts=3)

    assert server is fake_server
    assert port == 8051
    assert attempted_ports == [8050, 8051]


def test_browser_opens_only_after_ready(monkeypatch) -> None:
    opened: list[str] = []

    monkeypatch.setattr(desktop_launcher, "wait_for_health", lambda *args, **kwargs: True)
    monkeypatch.setattr(desktop_launcher.webbrowser, "open", lambda url, new=0, autoraise=True: opened.append(url) or True)

    assert desktop_launcher.open_browser_when_ready("http://127.0.0.1:8050/") is True
    assert opened == ["http://127.0.0.1:8050/"]

    opened.clear()
    monkeypatch.setattr(desktop_launcher, "wait_for_health", lambda *args, **kwargs: False)

    assert desktop_launcher.open_browser_when_ready("http://127.0.0.1:8050/") is False
    assert opened == []


def test_pyinstaller_spec_includes_launcher_assets_pages_and_workbook() -> None:
    spec = (ROOT / "pv_app.spec").read_text(encoding="utf-8")

    assert "desktop_launcher.py" in spec
    assert '"assets"' in spec
    assert '"pages"' in spec
    assert '"PV_inputs.xlsx"' in spec
    assert '"pages.workbench"' in spec
    assert '"pages.compare"' in spec
    assert '"pages.risk"' in spec
