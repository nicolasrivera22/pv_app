from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
from threading import Lock
import time

from .runtime_paths import private_config_root


logger = logging.getLogger(__name__)

ADMIN_PIN_SETUP_COMMAND = "python -m services.admin_pin_cli set-pin"
ADMIN_PIN_FILENAME = "admin_pin.json"
PBKDF2_ITERATIONS = 240_000
_ACCESS_LOCK = Lock()
_UNLOCKED_SESSION_IDS: set[str] = set()


def admin_pin_path() -> Path:
    return (private_config_root() / "security" / ADMIN_PIN_FILENAME).resolve()


def _security_root() -> Path:
    return admin_pin_path().parent


def _ensure_security_root() -> Path:
    root = _security_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, 0o700)
    except OSError:
        logger.debug("admin_access event=chmod_dir_failed path=%s", root, exc_info=True)
    return root


def _normalize_pin(pin: str | int | None) -> str:
    value = "" if pin is None else str(pin).strip()
    if not value or not value.isdigit():
        raise ValueError("Admin PIN must contain digits only.")
    return value


def _write_private_json(path: Path, payload: dict[str, object]) -> None:
    _ensure_security_root()
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(encoded)
    try:
        os.chmod(path, 0o600)
    except OSError:
        logger.debug("admin_access event=chmod_file_failed path=%s", path, exc_info=True)


def _load_pin_record() -> dict[str, object] | None:
    path = admin_pin_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    required_keys = {"algorithm", "iterations", "salt", "hash"}
    if not required_keys.issubset(payload):
        return None
    return payload


def admin_pin_configured() -> bool:
    return _load_pin_record() is not None


def set_admin_pin(pin: str | int) -> Path:
    normalized_pin = _normalize_pin(pin)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", normalized_pin.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    payload = {
        "version": 1,
        "algorithm": "pbkdf2_sha256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "hash": base64.b64encode(digest).decode("ascii"),
        "updated_at": time.time(),
    }
    path = admin_pin_path()
    _write_private_json(path, payload)
    return path


def verify_admin_pin(pin: str | int | None) -> bool:
    try:
        normalized_pin = _normalize_pin(pin)
    except ValueError:
        return False
    payload = _load_pin_record()
    if payload is None:
        return False
    try:
        iterations = int(payload["iterations"])
        salt = base64.b64decode(str(payload["salt"]).encode("ascii"))
        expected = base64.b64decode(str(payload["hash"]).encode("ascii"))
    except (TypeError, ValueError, KeyError, binascii.Error):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", normalized_pin.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)


def grant_admin_session_access(session_id: str) -> None:
    normalized = str(session_id or "").strip()
    if not normalized:
        return
    with _ACCESS_LOCK:
        _UNLOCKED_SESSION_IDS.add(normalized)


def is_admin_session_unlocked(session_id: str) -> bool:
    normalized = str(session_id or "").strip()
    if not normalized:
        return False
    with _ACCESS_LOCK:
        return normalized in _UNLOCKED_SESSION_IDS


def clear_admin_session_access(session_id: str) -> None:
    normalized = str(session_id or "").strip()
    if not normalized:
        return
    with _ACCESS_LOCK:
        _UNLOCKED_SESSION_IDS.discard(normalized)


def clear_all_admin_session_access() -> None:
    with _ACCESS_LOCK:
        _UNLOCKED_SESSION_IDS.clear()
