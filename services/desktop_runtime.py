from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any
import urllib.error
import urllib.request

from .runtime_paths import internal_runtime_root


APP_NAME = "PVWorkbench"
RUNTIME_FILENAME = "runtime.json"
STARTUP_LOCK_FILENAME = "startup.lock"
STARTUP_LOCK_STALE_AFTER_S = 60.0


@dataclass(frozen=True)
class RuntimeRecord:
    app_name: str
    version: str | None
    pid: int
    host: str
    port: int
    app_url: str
    startup_ts: float
    instance_token: str
    frozen: bool


@dataclass
class StartupLock:
    path: Path
    fd: int | None
    metadata: dict[str, Any]

    def release(self) -> None:
        fd = self.fd
        if fd is not None:
            self.fd = None
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def desktop_runtime_dir() -> Path:
    root = internal_runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def runtime_file_path() -> Path:
    return (desktop_runtime_dir() / RUNTIME_FILENAME).resolve()


def startup_lock_path() -> Path:
    return (desktop_runtime_dir() / STARTUP_LOCK_FILENAME).resolve()


def load_runtime_record() -> RuntimeRecord | None:
    path = runtime_file_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeRecord(
            app_name=str(payload["app_name"]),
            version=payload.get("version"),
            pid=int(payload["pid"]),
            host=str(payload["host"]),
            port=int(payload["port"]),
            app_url=str(payload["app_url"]),
            startup_ts=float(payload["startup_ts"]),
            instance_token=str(payload["instance_token"]),
            frozen=bool(payload["frozen"]),
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def write_runtime_record(record: RuntimeRecord) -> Path:
    path = runtime_file_path()
    payload = asdict(record)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        temp_path = Path(handle.name)
    temp_path.replace(path)
    return path


def remove_runtime_record(*, expected_token: str | None = None) -> bool:
    path = runtime_file_path()
    if expected_token is not None:
        record = load_runtime_record()
        if record is None or record.instance_token != str(expected_token):
            return False
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False


def fetch_desktop_health(app_url: str, *, timeout_s: float = 0.75) -> dict[str, Any] | None:
    health_url = app_url.rstrip("/") + "/__desktop/health"
    try:
        with urllib.request.urlopen(health_url, timeout=timeout_s) as response:
            if int(getattr(response, "status", 0)) < 200 or int(getattr(response, "status", 0)) >= 300:
                return None
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def validate_runtime_record(record: RuntimeRecord | None) -> dict[str, Any] | None:
    if record is None:
        return None
    payload = fetch_desktop_health(record.app_url)
    if not payload:
        return None
    if str(payload.get("status") or "") != "ok":
        return None
    if str(payload.get("instance_token") or "") != record.instance_token:
        return None
    return payload


def acquire_startup_lock(*, timeout_s: float = 10.0, stale_after_s: float = STARTUP_LOCK_STALE_AFTER_S) -> StartupLock:
    path = startup_lock_path()
    deadline = time.monotonic() + timeout_s
    while True:
        nonce = f"{os.getpid()}-{time.time_ns()}"
        metadata = {"pid": os.getpid(), "startup_ts": time.time(), "nonce": nonce}
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps(metadata).encode("utf-8"))
            os.fsync(fd)
            return StartupLock(path=path, fd=fd, metadata=metadata)
        except FileExistsError:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                startup_ts = float(payload.get("startup_ts", 0.0))
            except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
                startup_ts = 0.0
            if startup_ts and (time.time() - startup_ts) > stale_after_s:
                try:
                    path.unlink()
                    continue
                except FileNotFoundError:
                    continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Could not acquire startup lock at {path}.")
            time.sleep(0.1)
