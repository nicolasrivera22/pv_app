from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from threading import Lock
from typing import Any


DraftRows = list[dict[str, Any]]
DraftTables = dict[str, DraftRows]


@dataclass(frozen=True)
class WorkspaceDraftState:
    config_overrides: dict[str, Any] = field(default_factory=dict)
    table_rows: DraftTables = field(default_factory=dict)
    revision: int = 0
    updated_at: float = 0.0
    project_slug: str | None = None


_LOCK = Lock()
_DRAFTS: dict[tuple[str, str], WorkspaceDraftState] = {}


def clear_workspace_drafts() -> None:
    with _LOCK:
        _DRAFTS.clear()


def get_workspace_draft(session_id: str, scenario_id: str) -> WorkspaceDraftState | None:
    with _LOCK:
        return _DRAFTS.get((str(session_id), str(scenario_id)))


def has_workspace_draft(session_id: str, scenario_id: str) -> bool:
    return get_workspace_draft(session_id, scenario_id) is not None


def upsert_workspace_draft(
    session_id: str,
    scenario_id: str,
    *,
    config_overrides: dict[str, Any] | None = None,
    owned_config_fields: set[str] | None = None,
    table_rows: DraftTables | None = None,
    owned_tables: set[str] | None = None,
    project_slug: str | None = None,
) -> WorkspaceDraftState | None:
    key = (str(session_id), str(scenario_id))
    now = time.time()
    owned_config = {str(field) for field in (owned_config_fields or set()) if str(field).strip()}
    owned_table_keys = {str(name) for name in (owned_tables or set()) if str(name).strip()}
    next_config = {str(field): value for field, value in dict(config_overrides or {}).items()}
    next_tables = {
        str(name): [dict(row) for row in rows]
        for name, rows in dict(table_rows or {}).items()
    }

    with _LOCK:
        current = _DRAFTS.get(key) or WorkspaceDraftState(project_slug=project_slug)
        merged_config = dict(current.config_overrides)
        for field in owned_config:
            merged_config.pop(field, None)
        merged_config.update(next_config)

        merged_tables: DraftTables = {
            name: [dict(row) for row in rows]
            for name, rows in current.table_rows.items()
        }
        for table_name in owned_table_keys:
            merged_tables.pop(table_name, None)
        for table_name, rows in next_tables.items():
            merged_tables[table_name] = [dict(row) for row in rows]

        if not merged_config and not merged_tables:
            _DRAFTS.pop(key, None)
            return None

        revision = current.revision + 1
        draft = WorkspaceDraftState(
            config_overrides=merged_config,
            table_rows=merged_tables,
            revision=revision,
            updated_at=now,
            project_slug=project_slug if project_slug is not None else current.project_slug,
        )
        _DRAFTS[key] = draft
        return draft


def clear_workspace_draft(session_id: str, scenario_id: str) -> None:
    with _LOCK:
        _DRAFTS.pop((str(session_id), str(scenario_id)), None)


def clear_session_workspace_drafts(session_id: str) -> None:
    normalized = str(session_id)
    with _LOCK:
        doomed = [key for key in _DRAFTS if key[0] == normalized]
        for key in doomed:
            _DRAFTS.pop(key, None)


def clear_project_workspace_drafts(session_id: str, project_slug: str | None) -> None:
    normalized_session = str(session_id)
    normalized_slug = None if project_slug in (None, "") else str(project_slug)
    with _LOCK:
        doomed = [
            key
            for key, draft in _DRAFTS.items()
            if key[0] == normalized_session and draft.project_slug == normalized_slug
        ]
        for key in doomed:
            _DRAFTS.pop(key, None)


def bind_workspace_draft_project(session_id: str, scenario_id: str, project_slug: str | None) -> WorkspaceDraftState | None:
    key = (str(session_id), str(scenario_id))
    normalized_slug = None if project_slug in (None, "") else str(project_slug)
    with _LOCK:
        current = _DRAFTS.get(key)
        if current is None:
            return None
        updated = replace(current, project_slug=normalized_slug)
        _DRAFTS[key] = updated
        return updated
