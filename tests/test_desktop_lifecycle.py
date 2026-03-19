from __future__ import annotations

from pathlib import Path
import time

import pytest

from app import create_app
from services.desktop_lifecycle import DesktopLifecycleConfig, DesktopLifecycleManager, desktop_lifecycle
from services.desktop_runtime import (
    RuntimeRecord,
    acquire_startup_lock,
    load_runtime_record,
    remove_runtime_record,
    startup_lock_path,
    validate_runtime_record,
    write_runtime_record,
)


@pytest.fixture(autouse=True)
def reset_desktop_lifecycle() -> None:
    desktop_lifecycle.reset()
    yield
    desktop_lifecycle.reset()


def test_validate_runtime_record_rejects_token_mismatch(monkeypatch) -> None:
    record = RuntimeRecord(
        app_name="PVWorkbench",
        version=None,
        pid=123,
        host="127.0.0.1",
        port=8050,
        app_url="http://127.0.0.1:8050/",
        startup_ts=1.0,
        instance_token="expected-token",
        frozen=True,
    )
    monkeypatch.setattr(
        "services.desktop_runtime.fetch_desktop_health",
        lambda app_url, timeout_s=0.75: {"status": "ok", "instance_token": "other-token", "pid": 123, "port": 8050},
    )

    assert validate_runtime_record(record) is None


def test_runtime_record_cleanup_is_token_owned(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("services.desktop_runtime.desktop_runtime_dir", lambda: tmp_path)
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
    write_runtime_record(record)

    assert remove_runtime_record(expected_token="token-b") is False
    assert load_runtime_record() is not None
    assert remove_runtime_record(expected_token="token-a") is True
    assert load_runtime_record() is None


def test_startup_lock_is_atomic_and_supports_stale_recovery(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("services.desktop_runtime.desktop_runtime_dir", lambda: tmp_path)

    first_lock = acquire_startup_lock(timeout_s=0.2)
    with pytest.raises(TimeoutError):
        acquire_startup_lock(timeout_s=0.2)

    first_lock.release()

    stale_path = startup_lock_path()
    stale_path.write_text('{"pid": 999, "startup_ts": 1.0, "nonce": "stale"}', encoding="utf-8")
    monkeypatch.setattr("services.desktop_runtime.time.time", lambda: 120.0)
    recovered_lock = acquire_startup_lock(timeout_s=0.2, stale_after_s=60.0)

    assert recovered_lock.metadata["pid"] > 0
    assert "startup_ts" in recovered_lock.metadata
    recovered_lock.release()


def test_desktop_lifecycle_startup_and_last_client_graces() -> None:
    manager = DesktopLifecycleManager()
    manager.configure(
        instance_token="token",
        port=8050,
        single_instance_enabled=True,
        auto_shutdown_enabled=True,
        frozen=True,
        config=DesktopLifecycleConfig(startup_grace_s=30.0, last_client_grace_s=5.0, stale_client_timeout_s=15.0),
        now=0.0,
    )

    assert manager.should_shutdown(now=20.0) is False
    assert manager.should_shutdown(now=31.0) is True

    manager.configure(
        instance_token="token",
        port=8050,
        single_instance_enabled=True,
        auto_shutdown_enabled=True,
        frozen=True,
        config=DesktopLifecycleConfig(startup_grace_s=30.0, last_client_grace_s=5.0, stale_client_timeout_s=15.0),
        now=0.0,
    )
    assert manager.record_heartbeat("tab-a", "token", now=1.0) is True
    assert manager.should_shutdown(now=10.0) is False
    assert manager.record_disconnect("tab-a", "token", now=2.0) is True
    assert manager.should_shutdown(now=6.0) is False
    assert manager.should_shutdown(now=7.1) is True


def test_desktop_lifecycle_handles_multiple_tabs_and_missed_unload() -> None:
    manager = DesktopLifecycleManager()
    manager.configure(
        instance_token="token",
        port=8050,
        single_instance_enabled=True,
        auto_shutdown_enabled=True,
        frozen=True,
        config=DesktopLifecycleConfig(startup_grace_s=30.0, last_client_grace_s=5.0, stale_client_timeout_s=15.0),
        now=0.0,
    )
    manager.record_heartbeat("tab-a", "token", now=1.0)
    manager.record_heartbeat("tab-b", "token", now=2.0)
    manager.record_disconnect("tab-a", "token", now=3.0)

    assert manager.active_client_count(now=3.0) == 1
    assert manager.should_shutdown(now=10.0) is False

    assert manager.active_client_count(now=18.0) == 0
    assert manager.should_shutdown(now=18.0) is False
    assert manager.should_shutdown(now=23.1) is True


def test_desktop_lifecycle_accepts_distinct_client_ids_for_duplicated_tabs() -> None:
    manager = DesktopLifecycleManager()
    manager.configure(
        instance_token="token",
        port=8050,
        single_instance_enabled=True,
        auto_shutdown_enabled=True,
        frozen=True,
        now=0.0,
    )

    manager.record_heartbeat("tab-a-copy-1", "token", now=1.0)
    manager.record_heartbeat("tab-a-copy-2", "token", now=1.5)

    assert manager.active_client_count(now=2.0) == 2


def test_desktop_lifecycle_asset_uses_fresh_page_load_identity() -> None:
    script = Path("assets/desktop_lifecycle.js").read_text(encoding="utf-8")

    assert "crypto.randomUUID" in script
    assert "sessionStorage" not in script


def test_desktop_routes_report_dev_defaults_and_accept_form_payloads() -> None:
    app = create_app()
    client = app.server.test_client()

    health_response = client.get("/__desktop/health")
    assert health_response.status_code == 200
    assert health_response.get_json()["single_instance_enabled"] is False
    assert health_response.get_json()["auto_shutdown_enabled"] is False

    desktop_lifecycle.configure(
        instance_token="token",
        port=8050,
        single_instance_enabled=True,
        auto_shutdown_enabled=True,
        frozen=True,
        now=0.0,
    )

    heartbeat = client.post(
        "/__desktop/client/heartbeat",
        data={"client_id": "tab-a", "instance_token": "token"},
    )
    assert heartbeat.status_code == 200
    assert heartbeat.get_json()["active_client_count"] == 1

    mismatch = client.post(
        "/__desktop/client/heartbeat",
        data={"client_id": "tab-b", "instance_token": "wrong"},
    )
    assert mismatch.status_code == 409

    disconnect = client.post(
        "/__desktop/client/disconnect",
        data={"client_id": "tab-a", "instance_token": "token"},
    )
    assert disconnect.status_code == 200
    assert disconnect.get_json()["active_client_count"] == 0
