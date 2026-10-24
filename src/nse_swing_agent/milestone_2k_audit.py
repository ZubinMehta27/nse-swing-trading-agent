"""Pure classification helpers for the Milestone 2K evidence audit."""

from __future__ import annotations


def classify_bar_presence(calendar_status: str, *, observed: bool, candidate: bool) -> str:
    """Classify a symbol bar against a sourced session status without inferring holidays."""
    status = calendar_status.strip().upper()
    if status not in {"SESSION", "SPECIAL_SESSION", "HOLIDAY", "WEEKEND", "WEEKEND_HOLIDAY"}:
        raise ValueError(f"unsupported calendar status: {calendar_status!r}")
    if observed and status in {"HOLIDAY", "WEEKEND", "WEEKEND_HOLIDAY"}:
        return "observed_bar_on_calendar_non_session_review"
    if observed and status == "SPECIAL_SESSION":
        return "observed_special_session_bar"
    if observed:
        return "observed_expected_session_bar"
    if status in {"WEEKEND", "WEEKEND_HOLIDAY"}:
        return "weekend_no_bar_expected"
    if status == "HOLIDAY":
        return "confirmed_exchange_holiday"
    if candidate:
        return "provider_bar_missing_official_candidate_available_unmerged"
    if status == "SPECIAL_SESSION":
        return "missing_expected_special_session_unresolved"
    return "missing_expected_session_unresolved"
