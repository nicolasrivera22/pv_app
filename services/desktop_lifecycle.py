from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import os
import time
from typing import Any


DEFAULT_HEARTBEAT_INTERVAL_S = 5.0
DEFAULT_STALE_CLIENT_TIMEOUT_S = 15.0
DEFAULT_LAST_CLIENT_GRACE_S = 5.0
DEFAULT_STARTUP_GRACE_S = 30.0


@dataclass(frozen=True)
class DesktopLifecycleConfig:
    heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S
    stale_client_timeout_s: float = DEFAULT_STALE_CLIENT_TIMEOUT_S
    last_client_grace_s: float = DEFAULT_LAST_CLIENT_GRACE_S
    startup_grace_s: float = DEFAULT_STARTUP_GRACE_S


class DesktopLifecycleManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._instance_token: str | None = None
            self._pid: int | None = None
            self._port: int | None = None
            self._frozen = False
            self._single_instance_enabled = False
            self._auto_shutdown_enabled = False
            self._configured_at = 0.0
            self._connected_once = False
            self._empty_since: float | None = None
            self._clients: dict[str, float] = {}
            self._config = DesktopLifecycleConfig()

    def configure(
        self,
        *,
        instance_token: str,
        port: int,
        single_instance_enabled: bool,
        auto_shutdown_enabled: bool,
        frozen: bool,
        config: DesktopLifecycleConfig | None = None,
        now: float | None = None,
    ) -> None:
        with self._lock:
            current_time = time.monotonic() if now is None else float(now)
            self._instance_token = str(instance_token)
            self._pid = os.getpid()
            self._port = int(port)
            self._frozen = bool(frozen)
            self._single_instance_enabled = bool(single_instance_enabled)
            self._auto_shutdown_enabled = bool(auto_shutdown_enabled)
            self._configured_at = current_time
            self._connected_once = False
            self._empty_since = None
            self._clients = {}
            self._config = config or DesktopLifecycleConfig()

    @property
    def instance_token(self) -> str | None:
        with self._lock:
            return self._instance_token

    @property
    def auto_shutdown_enabled(self) -> bool:
        with self._lock:
            return self._auto_shutdown_enabled

    @property
    def single_instance_enabled(self) -> bool:
        with self._lock:
            return self._single_instance_enabled

    def _prune_locked(self, now: float) -> None:
        stale_before = now - self._config.stale_client_timeout_s
        stale_ids = [client_id for client_id, last_seen in self._clients.items() if last_seen < stale_before]
        for client_id in stale_ids:
            self._clients.pop(client_id, None)
        if self._connected_once and not self._clients and self._empty_since is None:
            self._empty_since = now

    def active_client_count(self, *, now: float | None = None) -> int:
        with self._lock:
            current_time = time.monotonic() if now is None else float(now)
            self._prune_locked(current_time)
            return len(self._clients)

    def record_heartbeat(self, client_id: str, token: str, *, now: float | None = None) -> bool:
        with self._lock:
            if not self._instance_token or str(token) != self._instance_token:
                return False
            current_time = time.monotonic() if now is None else float(now)
            self._clients[str(client_id)] = current_time
            self._connected_once = True
            self._empty_since = None
            self._prune_locked(current_time)
            return True

    def record_disconnect(self, client_id: str, token: str, *, now: float | None = None) -> bool:
        with self._lock:
            if not self._instance_token or str(token) != self._instance_token:
                return False
            current_time = time.monotonic() if now is None else float(now)
            self._clients.pop(str(client_id), None)
            self._prune_locked(current_time)
            if self._connected_once and not self._clients:
                self._empty_since = current_time
            return True

    def should_shutdown(self, *, now: float | None = None) -> bool:
        with self._lock:
            if not self._auto_shutdown_enabled:
                return False
            current_time = time.monotonic() if now is None else float(now)
            self._prune_locked(current_time)
            if not self._connected_once:
                return (current_time - self._configured_at) >= self._config.startup_grace_s
            if self._clients:
                return False
            if self._empty_since is None:
                return False
            return (current_time - self._empty_since) >= self._config.last_client_grace_s

    def health_payload(self, *, now: float | None = None) -> dict[str, Any]:
        with self._lock:
            current_time = time.monotonic() if now is None else float(now)
            self._prune_locked(current_time)
            return {
                "status": "ok",
                "instance_token": self._instance_token,
                "pid": self._pid,
                "port": self._port,
                "frozen": self._frozen,
                "single_instance_enabled": self._single_instance_enabled,
                "auto_shutdown_enabled": self._auto_shutdown_enabled,
                "active_client_count": len(self._clients),
            }


desktop_lifecycle = DesktopLifecycleManager()
