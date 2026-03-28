from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CLIENT_SAFE_GROUPS = {
    "Demanda y Perfil",
    "Sol y módulos",
    "Semilla",
    "Restricción de Proporción Pico",
}
ADMIN_ONLY_GROUPS = {
    "Economía",
    "Inversor",
    "Precios",
    "Monte Carlo",
}
CLIENT_SAFE_BATTERY_EXPORT_FIELDS = {
    "include_battery",
    "optimize_battery",
    "export_allowed",
}
ADMIN_BATTERY_EXPORT_FIELDS = {
    "battery_name",
    "bat_DoD",
    "bat_coupling",
    "bat_eta_rt",
}


@dataclass(frozen=True)
class WorkspaceSectionPartition:
    client_safe_sections: list[dict[str, Any]]
    admin_sections: list[dict[str, Any]]


def _clone_section_with_fields(section: dict[str, Any], allowed_fields: set[str]) -> dict[str, Any] | None:
    basic = [dict(field) for field in section.get("basic", []) if field.get("field") in allowed_fields]
    advanced = [dict(field) for field in section.get("advanced", []) if field.get("field") in allowed_fields]
    if not basic and not advanced:
        return None
    cloned = {
        key: value
        for key, value in section.items()
        if key not in {"basic", "advanced"}
    }
    cloned["basic"] = basic
    cloned["advanced"] = advanced
    return cloned


def partition_assumption_sections(sections: list[dict[str, Any]]) -> WorkspaceSectionPartition:
    client_sections: list[dict[str, Any]] = []
    admin_sections: list[dict[str, Any]] = []
    for section in sections:
        group_key = str(section.get("group_key", "")).strip()
        if group_key in CLIENT_SAFE_GROUPS:
            client_sections.append(_clone_section_with_fields(section, {field["field"] for field in section.get("basic", []) + section.get("advanced", [])}) or dict(section))
            continue
        if group_key in ADMIN_ONLY_GROUPS:
            admin_sections.append(_clone_section_with_fields(section, {field["field"] for field in section.get("basic", []) + section.get("advanced", [])}) or dict(section))
            continue
        if group_key == "Controles de Batería y Exporte":
            client_slice = _clone_section_with_fields(section, CLIENT_SAFE_BATTERY_EXPORT_FIELDS)
            admin_slice = _clone_section_with_fields(section, ADMIN_BATTERY_EXPORT_FIELDS)
            if client_slice is not None:
                client_sections.append(client_slice)
            if admin_slice is not None:
                admin_sections.append(admin_slice)
    return WorkspaceSectionPartition(client_safe_sections=client_sections, admin_sections=admin_sections)
