from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from threading import Lock
from uuid import uuid4

from .scenario_session import hydrate_scenario_scan
from .types import ClientSessionState, ScenarioSessionState

MAX_SESSION_STATES = 12
SESSION_IDLE_TTL_SECONDS = 43_200


@dataclass
class _SessionEntry:
    state: ScenarioSessionState
    created_at: float
    last_access_at: float


_LOCK = Lock()
_SESSIONS: OrderedDict[str, _SessionEntry] = OrderedDict()


def _new_session_id() -> str:
    return f"session-{uuid4().hex[:12]}"


def _prune_locked(
    *,
    max_entries: int = MAX_SESSION_STATES,
    idle_ttl_seconds: int = SESSION_IDLE_TTL_SECONDS,
) -> None:
    now = time.time()
    expired = [
        session_id
        for session_id, entry in _SESSIONS.items()
        if idle_ttl_seconds > 0 and (now - entry.last_access_at) > idle_ttl_seconds
    ]
    for session_id in expired:
        _SESSIONS.pop(session_id, None)
    while len(_SESSIONS) > max_entries:
        _SESSIONS.popitem(last=False)


def prune_session_states(
    *,
    max_entries: int = MAX_SESSION_STATES,
    idle_ttl_seconds: int = SESSION_IDLE_TTL_SECONDS,
) -> None:
    with _LOCK:
        _prune_locked(max_entries=max_entries, idle_ttl_seconds=idle_ttl_seconds)


def clear_session_states() -> None:
    with _LOCK:
        _SESSIONS.clear()


def get_session_state(session_id: str) -> ScenarioSessionState | None:
    with _LOCK:
        entry = _SESSIONS.get(session_id)
        if entry is None:
            return None
        entry.last_access_at = time.time()
        _SESSIONS.move_to_end(session_id)
        return entry.state


def set_session_state(session_id: str, state: ScenarioSessionState) -> None:
    now = time.time()
    with _LOCK:
        existing = _SESSIONS.get(session_id)
        created_at = existing.created_at if existing is not None else now
        _SESSIONS[session_id] = _SessionEntry(
            state=state,
            created_at=created_at,
            last_access_at=now,
        )
        _SESSIONS.move_to_end(session_id)
        _prune_locked()


def _sync_client_state(
    client_state: ClientSessionState,
    session_state: ScenarioSessionState,
    *,
    revision: int | None = None,
) -> ClientSessionState:
    selected_candidate_keys = {
        scenario.scenario_id: scenario.selected_candidate_key
        for scenario in session_state.scenarios
        if scenario.selected_candidate_key is not None
    }
    return replace(
        client_state,
        active_scenario_id=session_state.active_scenario_id,
        comparison_scenario_ids=session_state.comparison_scenario_ids,
        design_comparison_candidate_keys=session_state.design_comparison_candidate_keys,
        selected_candidate_keys=selected_candidate_keys,
        project_slug=session_state.project_slug,
        project_name=session_state.project_name,
        project_dirty=session_state.project_dirty,
        revision=client_state.revision if revision is None else revision,
    )


def bootstrap_client_session(language: str = "es") -> ClientSessionState:
    client_state = ClientSessionState(session_id=_new_session_id(), language=language)
    set_session_state(client_state.session_id, ScenarioSessionState.empty())
    return client_state


def resolve_client_session(payload: dict | None, *, language: str = "es") -> tuple[ClientSessionState, ScenarioSessionState]:
    client_state = ClientSessionState.from_payload(payload)
    if client_state is None:
        client_state = bootstrap_client_session(language=language)
        return client_state, get_session_state(client_state.session_id) or ScenarioSessionState.empty()

    session_state = get_session_state(client_state.session_id)
    if session_state is None:
        if client_state.project_slug:
            from .project_io import open_project

            session_state = open_project(client_state.project_slug)
        else:
            session_state = ScenarioSessionState.empty()
        client_state = replace(client_state, session_id=_new_session_id(), language=language)
        set_session_state(client_state.session_id, session_state)
    else:
        client_state = replace(client_state, language=language)
    return _sync_client_state(client_state, session_state), session_state


def commit_client_session(
    client_state: ClientSessionState,
    session_state: ScenarioSessionState,
    *,
    bump_revision: bool = True,
) -> ClientSessionState:
    revision = client_state.revision + 1 if bump_revision else client_state.revision
    set_session_state(client_state.session_id, session_state)
    return _sync_client_state(client_state, session_state, revision=revision)


def resolve_scenario_session(
    payload: dict | None,
    *,
    scenario_id: str | None = None,
    ensure_scan: bool = False,
    language: str = "es",
) -> tuple[ClientSessionState, ScenarioSessionState]:
    client_state, session_state = resolve_client_session(payload, language=language)
    if not ensure_scan:
        return client_state, session_state
    target_id = scenario_id or session_state.active_scenario_id
    if target_id is None:
        return client_state, session_state
    next_state = hydrate_scenario_scan(session_state, target_id)
    if next_state is not session_state:
        set_session_state(client_state.session_id, next_state)
        session_state = next_state
    return _sync_client_state(client_state, session_state), session_state
