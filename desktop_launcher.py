from __future__ import annotations

import multiprocessing
import os
import secrets
import time
from threading import Event, Thread
import urllib.error
import urllib.request
import webbrowser
from typing import Any

from werkzeug.serving import BaseWSGIServer, make_server

from services.desktop_lifecycle import DesktopLifecycleConfig, desktop_lifecycle
from services.desktop_runtime import (
    RuntimeRecord,
    acquire_startup_lock,
    fetch_desktop_health,
    load_runtime_record,
    remove_runtime_record,
    validate_runtime_record,
    write_runtime_record,
)
from services.runtime_paths import configure_runtime_environment
from services.runtime_paths import is_frozen_runtime

configure_runtime_environment()

from app import app as dash_app


HOST = "127.0.0.1"
PREFERRED_PORT = 8050
PORT_ATTEMPTS = 15
HEALTH_TIMEOUT_S = 10.0
HEALTH_POLL_INTERVAL_S = 0.15
WATCHDOG_POLL_INTERVAL_S = 1.0
STARTUP_LOCK_TIMEOUT_S = 10.0


def _wsgi_app(app_or_server: Any):
    return getattr(app_or_server, "server", app_or_server)


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def single_instance_enabled() -> bool:
    return is_frozen_runtime() or _env_flag("PVW_DESKTOP_SINGLE_INSTANCE")


def auto_shutdown_enabled() -> bool:
    return is_frozen_runtime() or _env_flag("PVW_DESKTOP_AUTO_SHUTDOWN")


def wait_for_desktop_health(
    app_url: str,
    *,
    expected_token: str | None = None,
    timeout_s: float = HEALTH_TIMEOUT_S,
    poll_interval_s: float = HEALTH_POLL_INTERVAL_S,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        payload = fetch_desktop_health(app_url)
        if payload is not None and str(payload.get("status") or "") == "ok" and (
            expected_token is None or str(payload.get("instance_token") or "") == expected_token
        ):
            return payload
        time.sleep(poll_interval_s)
    return None


def create_local_server(
    app_or_server: Any,
    *,
    host: str = HOST,
    start_port: int = PREFERRED_PORT,
    max_attempts: int = PORT_ATTEMPTS,
) -> tuple[BaseWSGIServer, int]:
    last_error: OSError | None = None
    for port in range(start_port, start_port + max_attempts):
        try:
            return make_server(host, port, _wsgi_app(app_or_server), threaded=True), port
        except OSError as exc:
            last_error = exc
    raise RuntimeError(f"No se encontró un puerto libre entre {start_port} y {start_port + max_attempts - 1}.") from last_error


def wait_for_health(
    health_url: str,
    *,
    timeout_s: float = HEALTH_TIMEOUT_S,
    poll_interval_s: float = HEALTH_POLL_INTERVAL_S,
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=0.5) as response:
                if 200 <= int(getattr(response, "status", 0)) < 300:
                    return True
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(poll_interval_s)
    return False


def open_browser_when_ready(
    app_url: str,
    *,
    timeout_s: float = HEALTH_TIMEOUT_S,
) -> bool:
    health_url = app_url.rstrip("/") + "/healthz"
    if not wait_for_health(health_url, timeout_s=timeout_s):
        return False
    webbrowser.open(app_url, new=2, autoraise=True)
    return True


def _new_instance_token() -> str:
    return secrets.token_urlsafe(18)


def _desktop_config() -> DesktopLifecycleConfig:
    return DesktopLifecycleConfig(
        heartbeat_interval_s=5.0,
        stale_client_timeout_s=15.0,
        last_client_grace_s=5.0,
        startup_grace_s=30.0,
    )


def _start_shutdown_watchdog(server: BaseWSGIServer, stop_event: Event) -> Thread:
    def _watchdog() -> None:
        while not stop_event.wait(WATCHDOG_POLL_INTERVAL_S):
            if desktop_lifecycle.should_shutdown():
                server.shutdown()
                return

    thread = Thread(target=_watchdog, daemon=True)
    thread.start()
    return thread


def _finalize_desktop_startup(
    app_url: str,
    *,
    instance_token: str,
    port: int,
    startup_lock,
    should_write_runtime: bool,
) -> None:
    try:
        payload = wait_for_desktop_health(app_url, expected_token=instance_token)
        if payload is not None and should_write_runtime:
            write_runtime_record(
                RuntimeRecord(
                    app_name="PVWorkbench",
                    version=None,
                    pid=os.getpid(),
                    host=HOST,
                    port=port,
                    app_url=app_url,
                    startup_ts=time.time(),
                    instance_token=instance_token,
                    frozen=is_frozen_runtime(),
                )
            )
        if payload is not None:
            webbrowser.open(app_url, new=2, autoraise=True)
    finally:
        if startup_lock is not None:
            startup_lock.release()


def main() -> None:
    multiprocessing.freeze_support()
    use_single_instance = single_instance_enabled()
    use_auto_shutdown = auto_shutdown_enabled()
    startup_lock = None

    if use_single_instance:
        startup_lock = acquire_startup_lock(timeout_s=STARTUP_LOCK_TIMEOUT_S)
        existing_record = load_runtime_record()
        existing_health = validate_runtime_record(existing_record)
        if existing_record is not None and existing_health is not None:
            startup_lock.release()
            webbrowser.open(existing_record.app_url, new=2, autoraise=True)
            return
        remove_runtime_record()

    try:
        server, port = create_local_server(dash_app, host=HOST, start_port=PREFERRED_PORT, max_attempts=PORT_ATTEMPTS)
    except BaseException:
        if startup_lock is not None:
            startup_lock.release()
        raise
    app_url = f"http://{HOST}:{port}/"
    instance_token = _new_instance_token() if (use_single_instance or use_auto_shutdown) else ""
    if use_single_instance or use_auto_shutdown:
        desktop_lifecycle.configure(
            instance_token=instance_token,
            port=port,
            single_instance_enabled=use_single_instance,
            auto_shutdown_enabled=use_auto_shutdown,
            frozen=is_frozen_runtime(),
            config=_desktop_config(),
        )
    else:
        desktop_lifecycle.reset()

    if use_single_instance or use_auto_shutdown:
        Thread(
            target=_finalize_desktop_startup,
            args=(app_url,),
            kwargs={
                "instance_token": instance_token,
                "port": port,
                "startup_lock": startup_lock,
                "should_write_runtime": use_single_instance,
            },
            daemon=True,
        ).start()
    else:
        Thread(target=open_browser_when_ready, args=(app_url,), daemon=True).start()

    stop_event = Event()
    watchdog_thread = _start_shutdown_watchdog(server, stop_event) if use_auto_shutdown else None

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        if watchdog_thread is not None:
            watchdog_thread.join(timeout=1.5)
        if use_single_instance:
            remove_runtime_record(expected_token=instance_token)
        if startup_lock is not None:
            startup_lock.release()
        server.server_close()
        desktop_lifecycle.reset()


if __name__ == "__main__":
    main()
