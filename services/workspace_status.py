from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResultsStatusDigest:
    state: str
    tone: str
    title_key: str
    body_key: str
    cta_href: str | None = None
    cta_label_key: str | None = None


def resolve_results_status_digest(active) -> ResultsStatusDigest | None:
    if active is None:
        return ResultsStatusDigest(
            state="no_active",
            tone="neutral",
            title_key="workspace.results_digest.no_active.title",
            body_key="workspace.results_digest.no_active.body",
            cta_href="/assumptions",
            cta_label_key="workspace.results_digest.go_assumptions",
        )
    has_errors = any(issue.level == "error" for issue in active.config_bundle.issues)
    if has_errors:
        return ResultsStatusDigest(
            state="validation_blocked",
            tone="warning",
            title_key="workspace.results_digest.validation_blocked.title",
            body_key="workspace.results_digest.validation_blocked.body",
            cta_href="/assumptions",
            cta_label_key="workspace.results_digest.go_assumptions",
        )
    if active.scan_result is None:
        return ResultsStatusDigest(
            state="no_scan",
            tone="neutral",
            title_key="workspace.results_digest.no_scan.title",
            body_key="workspace.results_digest.no_scan.body",
            cta_href="/assumptions",
            cta_label_key="workspace.results_digest.go_assumptions",
        )
    if active.dirty:
        return ResultsStatusDigest(
            state="stale",
            tone="warning",
            title_key="workspace.results_digest.stale.title",
            body_key="workspace.results_digest.stale.body",
            cta_href="/assumptions",
            cta_label_key="workspace.results_digest.go_assumptions",
        )
    return None
