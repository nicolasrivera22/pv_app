from __future__ import annotations

import shutil
import time
from pathlib import Path

from app import create_app
import desktop_launcher
import pytest
from services import io_excel
from services.desktop_lifecycle import DesktopLifecycleConfig, desktop_lifecycle
from services.desktop_runtime import RuntimeRecord
from services.runtime_paths import (
    assets_dir,
    bundled_quick_guide_path,
    bundled_workbook_path,
    default_results_root,
    pages_dir,
    resource_root,
    user_root,
)


ROOT = Path(__file__).resolve().parent.parent


class _FakeLock:
    def __init__(self) -> None:
        self.release_calls = 0

    def release(self) -> None:
        self.release_calls += 1


class _FakeServer:
    def __init__(self) -> None:
        self.shutdown_calls = 0
        self.closed = False

    def serve_forever(self) -> None:
        while self.shutdown_calls == 0:
            time.sleep(0.01)

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def server_close(self) -> None:
        self.closed = True


def test_runtime_paths_resolve_to_repo_root_in_source_mode() -> None:
    assert resource_root() == ROOT
    assert user_root() == ROOT
    assert assets_dir() == ROOT / "assets"
    assert pages_dir() == ROOT / "pages"
    assert bundled_workbook_path() == ROOT / "PV_inputs.xlsx"
    assert bundled_quick_guide_path() == ROOT / "PVWorkbench_Guia_Rapida.html"


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
    assert bundled_quick_guide_path() == (resource_dir / "PVWorkbench_Guia_Rapida.html").resolve()
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
    desktop_response = client.get("/__desktop/health")
    help_response = client.get("/help/guia-rapida")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert desktop_response.status_code == 200
    assert desktop_response.get_json()["single_instance_enabled"] is False
    assert desktop_response.get_json()["auto_shutdown_enabled"] is False
    assert help_response.status_code == 200
    assert "PVWorkbench — Guía rápida" in help_response.get_data(as_text=True)
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


def test_create_local_server_raises_when_all_candidate_ports_are_busy(monkeypatch) -> None:
    attempted_ports: list[int] = []

    def fake_make_server(host, port, app, threaded=True):
        attempted_ports.append(port)
        raise OSError("busy")

    monkeypatch.setattr(desktop_launcher, "make_server", fake_make_server)

    with pytest.raises(RuntimeError, match=r"No se encontró un puerto libre entre 8050 y 8052\."):
        desktop_launcher.create_local_server(object(), start_port=8050, max_attempts=3)

    assert attempted_ports == [8050, 8051, 8052]


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


def test_dev_mode_defaults_disable_single_instance_and_auto_shutdown(monkeypatch) -> None:
    monkeypatch.setattr(desktop_launcher, "is_frozen_runtime", lambda: False)
    monkeypatch.delenv("PVW_DESKTOP_SINGLE_INSTANCE", raising=False)
    monkeypatch.delenv("PVW_DESKTOP_AUTO_SHUTDOWN", raising=False)

    assert desktop_launcher.single_instance_enabled() is False
    assert desktop_launcher.auto_shutdown_enabled() is False

    monkeypatch.setenv("PVW_DESKTOP_SINGLE_INSTANCE", "1")
    monkeypatch.setenv("PVW_DESKTOP_AUTO_SHUTDOWN", "1")

    assert desktop_launcher.single_instance_enabled() is True
    assert desktop_launcher.auto_shutdown_enabled() is True


def test_packaged_launcher_reuses_existing_runtime(monkeypatch) -> None:
    desktop_lifecycle.reset()
    opened: list[str] = []
    lock = _FakeLock()
    record = RuntimeRecord(
        app_name="PVWorkbench",
        version=None,
        pid=123,
        host="127.0.0.1",
        port=8050,
        app_url="http://127.0.0.1:8050/",
        startup_ts=1.0,
        instance_token="token-a",
        frozen=True,
    )

    monkeypatch.setattr(desktop_launcher, "single_instance_enabled", lambda: True)
    monkeypatch.setattr(desktop_launcher, "auto_shutdown_enabled", lambda: False)
    monkeypatch.setattr(desktop_launcher, "acquire_startup_lock", lambda timeout_s=10.0: lock)
    monkeypatch.setattr(desktop_launcher, "load_runtime_record", lambda: record)
    monkeypatch.setattr(desktop_launcher, "validate_runtime_record", lambda current: {"status": "ok", "instance_token": "token-a"})
    monkeypatch.setattr(desktop_launcher, "create_local_server", lambda *args, **kwargs: pytest.fail("should not create a second server"))
    monkeypatch.setattr(desktop_launcher.webbrowser, "open", lambda url, new=0, autoraise=True: opened.append(url) or True)
    monkeypatch.setattr(desktop_launcher.multiprocessing, "freeze_support", lambda: None)

    desktop_launcher.main()

    assert opened == ["http://127.0.0.1:8050/"]
    assert lock.release_calls == 1


def test_packaged_launcher_ignores_stale_runtime_and_starts_fresh_server(monkeypatch) -> None:
    desktop_lifecycle.reset()
    lock = _FakeLock()
    server = _FakeServer()
    removals: list[str | None] = []
    started: list[bool] = []

    class _ImmediateThread:
        def __init__(self, target=None, args=(), kwargs=None, daemon=None):
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self):
            if self._target is not None:
                self._target(*self._args, **self._kwargs)

        def join(self, timeout=None):
            return None

    record = RuntimeRecord(
        app_name="PVWorkbench",
        version=None,
        pid=123,
        host="127.0.0.1",
        port=8050,
        app_url="http://127.0.0.1:8050/",
        startup_ts=1.0,
        instance_token="stale-token",
        frozen=True,
    )

    monkeypatch.setattr(desktop_launcher, "single_instance_enabled", lambda: True)
    monkeypatch.setattr(desktop_launcher, "auto_shutdown_enabled", lambda: False)
    monkeypatch.setattr(desktop_launcher, "acquire_startup_lock", lambda timeout_s=10.0: lock)
    monkeypatch.setattr(desktop_launcher, "load_runtime_record", lambda: record)
    monkeypatch.setattr(desktop_launcher, "validate_runtime_record", lambda current: None)
    monkeypatch.setattr(desktop_launcher, "remove_runtime_record", lambda expected_token=None: removals.append(expected_token) or True)
    monkeypatch.setattr(desktop_launcher, "create_local_server", lambda *args, **kwargs: started.append(True) or (server, 8050))
    monkeypatch.setattr(desktop_launcher, "wait_for_desktop_health", lambda *args, **kwargs: {"status": "ok", "instance_token": "fresh-token"})
    monkeypatch.setattr(desktop_launcher, "write_runtime_record", lambda record: None)
    monkeypatch.setattr(desktop_launcher.webbrowser, "open", lambda *args, **kwargs: True)
    monkeypatch.setattr(desktop_launcher, "Thread", _ImmediateThread)
    monkeypatch.setattr(desktop_launcher, "_new_instance_token", lambda: "fresh-token")
    monkeypatch.setattr(desktop_launcher.multiprocessing, "freeze_support", lambda: None)

    server.shutdown()
    desktop_launcher.main()

    assert started == [True]
    assert removals[0] is None


def test_packaged_watchdog_triggers_shutdown_and_token_owned_cleanup(monkeypatch) -> None:
    desktop_lifecycle.reset()
    lock = _FakeLock()
    server = _FakeServer()
    removals: list[str | None] = []

    monkeypatch.setattr(desktop_launcher, "single_instance_enabled", lambda: True)
    monkeypatch.setattr(desktop_launcher, "auto_shutdown_enabled", lambda: True)
    monkeypatch.setattr(desktop_launcher, "acquire_startup_lock", lambda timeout_s=10.0: lock)
    monkeypatch.setattr(desktop_launcher, "load_runtime_record", lambda: None)
    monkeypatch.setattr(desktop_launcher, "remove_runtime_record", lambda expected_token=None: removals.append(expected_token) or True)
    monkeypatch.setattr(desktop_launcher, "create_local_server", lambda *args, **kwargs: (server, 8050))
    monkeypatch.setattr(desktop_launcher, "wait_for_desktop_health", lambda *args, **kwargs: {"status": "ok", "instance_token": kwargs["expected_token"]})
    monkeypatch.setattr(desktop_launcher, "write_runtime_record", lambda record: None)
    monkeypatch.setattr(desktop_launcher.webbrowser, "open", lambda *args, **kwargs: True)
    monkeypatch.setattr(desktop_launcher, "_desktop_config", lambda: DesktopLifecycleConfig(startup_grace_s=0.0, last_client_grace_s=0.0, stale_client_timeout_s=0.1))
    monkeypatch.setattr(desktop_launcher, "_new_instance_token", lambda: "owned-token")
    monkeypatch.setattr(desktop_launcher, "WATCHDOG_POLL_INTERVAL_S", 0.01)
    monkeypatch.setattr(desktop_launcher.multiprocessing, "freeze_support", lambda: None)

    desktop_launcher.main()

    assert server.shutdown_calls >= 1
    assert server.closed is True
    assert removals[-1] == "owned-token"


def test_pyinstaller_spec_includes_launcher_assets_pages_and_workbook() -> None:
    spec = (ROOT / "pv_app.spec").read_text(encoding="utf-8")

    assert "desktop_launcher.py" in spec
    assert '"assets"' in spec
    assert '"pages"' in spec
    assert '"PV_inputs.xlsx"' in spec
    assert '"PVWorkbench_Guia_Rapida.html"' in spec
    assert '"pages.workbench"' in spec
    assert '"pages.compare"' in spec
    assert '"pages.risk"' in spec
    assert '"pages.help"' in spec
