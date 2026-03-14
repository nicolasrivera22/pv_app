from __future__ import annotations

import multiprocessing
import time
import urllib.error
import urllib.request
import webbrowser
from typing import Any

from werkzeug.serving import BaseWSGIServer, make_server

from services.runtime_paths import configure_runtime_environment

configure_runtime_environment()

from app import app as dash_app


HOST = "127.0.0.1"
PREFERRED_PORT = 8050
PORT_ATTEMPTS = 15
HEALTH_TIMEOUT_S = 10.0
HEALTH_POLL_INTERVAL_S = 0.15


def _wsgi_app(app_or_server: Any):
    return getattr(app_or_server, "server", app_or_server)


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


def main() -> None:
    multiprocessing.freeze_support()
    server, port = create_local_server(dash_app, host=HOST, start_port=PREFERRED_PORT, max_attempts=PORT_ATTEMPTS)
    app_url = f"http://{HOST}:{port}/"

    from threading import Thread

    Thread(target=open_browser_when_ready, args=(app_url,), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
