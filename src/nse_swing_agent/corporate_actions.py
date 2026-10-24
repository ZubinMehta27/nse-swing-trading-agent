"""Validated corporate-action inputs and deterministic position accounting.

Canonical action manifests are explicit reviewed inputs. Provider adjustment factors are
not interpreted as event terms. Unsupported events are deliberately blocking.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any


class ActionKind(StrEnum):
    DIVIDEND = "dividend"
    SPLIT = "split"
    BONUS = "bonus"
    RIGHTS = "rights"
    DEMERGER = "demerger"
    MERGER = "merger"
    BUYBACK = "buyback"
    DELISTING = "delisting"


class PaymentTimingKind(StrEnum):
    EXACT_DATE = "exact_date"
    DOCUMENTED_WINDOW = "documented_window"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DividendPaymentTiming:
    """Evidence-backed dividend cash timing; a window is never an exact date."""

    kind: PaymentTimingKind
    evidence_reference: str
    exact_date: date | None = None
    earliest_date: date | None = None
    latest_date: date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PaymentTimingKind):
            raise ValueError("payment timing kind must be a PaymentTimingKind")
        if not isinstance(self.evidence_reference, str) or not self.evidence_reference.strip():
            raise ValueError("payment timing evidence_reference is required")
        if self.kind == PaymentTimingKind.EXACT_DATE:
            if not isinstance(self.exact_date, date) or isinstance(self.exact_date, datetime):
                raise ValueError("exact-date timing requires an exact date")
            if self.earliest_date is not None or self.latest_date is not None:
                raise ValueError("exact-date timing cannot also specify window bounds")
        elif self.kind == PaymentTimingKind.DOCUMENTED_WINDOW:
            if (
                not isinstance(self.earliest_date, date)
                or isinstance(self.earliest_date, datetime)
                or not isinstance(self.latest_date, date)
                or isinstance(self.latest_date, datetime)
            ):
                raise ValueError("documented-window timing requires earliest and latest dates")
            if self.earliest_date > self.latest_date:
                raise ValueError("payment window earliest_date must not follow latest_date")
            if self.exact_date is not None:
                raise ValueError("documented-window timing cannot specify an exact date")
        elif any(
            value is not None for value in (self.exact_date, self.earliest_date, self.latest_date)
        ):
            raise ValueError("unknown payment timing cannot specify payment dates")


SUPPORTED_ACTIONS = {ActionKind.DIVIDEND, ActionKind.SPLIT, ActionKind.BONUS}


def _day(value: Any, field: str, *, optional: bool = False) -> date | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise ValueError(f"action {field} must be an ISO date")
    try:
        result = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"action {field} has invalid date {value!r}") from exc
    if result.isoformat() != value:
        raise ValueError(f"action {field} must use YYYY-MM-DD")
    return result


def _decimal(value: Any, field: str, *, optional: bool = False) -> Decimal | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or value is None:
        raise ValueError(f"action {field} is required and must be a positive decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"action {field} is not a decimal: {value!r}") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"action {field} must be finite and positive")
    return result


@dataclass(frozen=True, slots=True)
class CorporateAction:
    symbol: str
    kind: ActionKind
    ex_date: date
    source: str
    source_fingerprint: str
    retrieved_at: datetime
    verification_status: str
    isin: str | None = None
    record_date: date | None = None
    payment_date: date | None = None
    ratio_new_per_old: Decimal | None = None
    cash_per_share: Decimal | None = None
    currency: str | None = None
    payment_timing: DividendPaymentTiming | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ActionKind):
            raise ValueError("action kind must be a validated ActionKind")
        if not self.symbol.strip() or not self.source.strip():
            raise ValueError("action symbol and source are required")
        if len(self.source_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_fingerprint.lower()
        ):
            raise ValueError("action source_fingerprint must be a SHA-256 hex digest")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("action retrieved_at must be timezone-aware")
        if self.verification_status not in {"verified", "unverified", "ambiguous"}:
            raise ValueError("verification_status must be verified, unverified, or ambiguous")
        if self.kind in {ActionKind.SPLIT, ActionKind.BONUS}:
            if (
                not isinstance(self.ratio_new_per_old, Decimal)
                or not self.ratio_new_per_old.is_finite()
                or self.ratio_new_per_old <= 0
            ):
                raise ValueError(f"{self.kind} requires explicit ratio_new_per_old")
        if self.kind == ActionKind.DIVIDEND:
            if not isinstance(self.cash_per_share, Decimal) or not self.currency:
                raise ValueError("dividend requires cash_per_share and currency")
            if not self.cash_per_share.is_finite() or self.cash_per_share <= 0:
                raise ValueError("dividend cash_per_share must be finite and positive")
            if self.currency != "INR":
                raise ValueError("only explicitly denominated INR dividends are supported")
            timing = self.payment_timing
            if timing is None:
                if self.payment_date is None:
                    raise ValueError(
                        "dividend requires explicit payment_timing or a legacy payment_date"
                    )
                timing = DividendPaymentTiming(
                    PaymentTimingKind.EXACT_DATE,
                    f"{self.source} sha256:{self.source_fingerprint}",
                    exact_date=self.payment_date,
                )
                object.__setattr__(self, "payment_timing", timing)
            if not isinstance(timing, DividendPaymentTiming):
                raise ValueError("dividend payment_timing must be validated")
            if timing.kind == PaymentTimingKind.EXACT_DATE:
                if self.payment_date is not None and self.payment_date != timing.exact_date:
                    raise ValueError("payment_date conflicts with exact payment_timing")
                object.__setattr__(self, "payment_date", timing.exact_date)
            elif self.payment_date is not None:
                raise ValueError("payment_date conflicts with non-exact payment_timing")
        if self.record_date is not None and self.record_date < self.ex_date:
            raise ValueError("action record_date cannot precede ex_date")
        if self.payment_date is not None and self.payment_date < self.ex_date:
            raise ValueError("action payment_date cannot precede ex_date")
        if (
            self.record_date is not None
            and self.payment_date is not None
            and self.payment_date < self.record_date
        ):
            raise ValueError("action payment_date cannot precede record_date")
        if self.kind == ActionKind.DIVIDEND:
            assert self.payment_timing is not None
            timing_dates = (
                (self.payment_timing.exact_date,)
                if self.payment_timing.kind == PaymentTimingKind.EXACT_DATE
                else (
                    (self.payment_timing.earliest_date, self.payment_timing.latest_date)
                    if self.payment_timing.kind == PaymentTimingKind.DOCUMENTED_WINDOW
                    else ()
                )
            )
            for timing_date in timing_dates:
                assert timing_date is not None
                if timing_date < self.ex_date:
                    raise ValueError("payment timing cannot precede ex_date")
                if self.record_date is not None and timing_date < self.record_date:
                    raise ValueError("payment timing cannot precede record_date")
        elif self.payment_timing is not None:
            raise ValueError("payment_timing is only valid for dividend actions")
        if self.verification_status != "verified":
            raise ValueError("ambiguous or unverified corporate actions cannot be applied")


@dataclass(frozen=True, slots=True)
class ActionCoverage:
    start: date
    end: date
    complete: bool
    verified: bool
    source: str
    source_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.complete, bool) or not isinstance(self.verified, bool):
            raise ValueError("action coverage complete and verified fields must be booleans")
        if self.start > self.end:
            raise ValueError("action coverage start must be on or before end")
        if not self.complete or not self.verified:
            raise ValueError("action dataset coverage must be explicitly complete and verified")
        if not self.source:
            raise ValueError("action coverage source is required")
        if len(self.source_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.source_fingerprint.lower()
        ):
            raise ValueError("action coverage fingerprint must be a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class DividendReceivable:
    symbol: str
    ex_date: date
    payment_date: date | None
    amount: Decimal
    source_fingerprint: str
    payment_timing: DividendPaymentTiming

    def __post_init__(self) -> None:
        if not self.amount.is_finite() or self.amount <= 0:
            raise ValueError("dividend receivable amount must be positive and finite")
        if self.payment_timing.kind == PaymentTimingKind.EXACT_DATE:
            if self.payment_date != self.payment_timing.exact_date:
                raise ValueError("receivable payment_date conflicts with payment timing")
        elif self.payment_date is not None:
            raise ValueError("non-exact receivable cannot carry an exact payment_date")


class UncertainDividendPaymentTimingError(ValueError):
    """A held dividend position has a window or unknown cash timing."""

    def __init__(self, receivable: DividendReceivable) -> None:
        self.receivable = receivable
        timing = receivable.payment_timing
        self.ledger_entry = {
            "symbol": receivable.symbol,
            "type": "dividend_payment_timing_block",
            "ex_date": receivable.ex_date.isoformat(),
            "amount": str(receivable.amount),
            "timing_kind": timing.kind.value,
            "earliest_date": timing.earliest_date.isoformat() if timing.earliest_date else None,
            "latest_date": timing.latest_date.isoformat() if timing.latest_date else None,
            "payment_date": None,
            "cash_credited": False,
            "evidence_reference": timing.evidence_reference,
            "source_fingerprint": receivable.source_fingerprint,
            "status": "blocked_uncertain_cash_timing",
        }
        if timing.kind == PaymentTimingKind.DOCUMENTED_WINDOW:
            detail = f"window {timing.earliest_date} through {timing.latest_date}"
        else:
            detail = "unknown payment date"
        super().__init__(
            f"backtest blocked by dividend {detail} for {receivable.symbol} "
            f"on {receivable.ex_date}; evidence: {timing.evidence_reference}"
        )


def _load_payment_timing(value: Any) -> DividendPaymentTiming | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("payment_timing must be an object")
    try:
        return DividendPaymentTiming(
            kind=PaymentTimingKind(value["kind"]),
            evidence_reference=str(value["evidence_reference"]),
            exact_date=_day(value.get("exact_date"), "payment_timing.exact_date", optional=True),
            earliest_date=_day(
                value.get("earliest_date"), "payment_timing.earliest_date", optional=True
            ),
            latest_date=_day(value.get("latest_date"), "payment_timing.latest_date", optional=True),
        )
    except (KeyError, ValueError) as exc:
        raise ValueError(f"invalid payment_timing: {exc}") from exc


def load_action_manifest(path: Path) -> tuple[tuple[CorporateAction, ...], ActionCoverage]:
    """Load the canonical reviewed action manifest; raw provider JSON is not canonical."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("action manifest must be a JSON object")
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("events"), list):
        raise ValueError("action manifest requires schema_version 1.0 and events array")
    missing_top = {"source", "source_fingerprint", "retrieved_at", "coverage"} - payload.keys()
    if missing_top:
        raise ValueError("action manifest missing fields: " + ", ".join(sorted(missing_top)))
    if not isinstance(payload["source"], str) or not payload["source"].strip():
        raise ValueError("action manifest source must be a nonempty string")
    coverage_data = payload.get("coverage")
    if not isinstance(coverage_data, dict):
        raise ValueError("action manifest coverage object is required")
    coverage = ActionCoverage(
        _day(coverage_data.get("from"), "coverage.from"),
        _day(coverage_data.get("to"), "coverage.to"),
        coverage_data.get("complete") is True,
        coverage_data.get("verified") is True,
        str(payload.get("source", "")),
        str(payload.get("source_fingerprint", "")),
    )
    retrieved = datetime.fromisoformat(payload["retrieved_at"])
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise ValueError("action manifest retrieved_at must be timezone-aware")
    digest = str(payload["source_fingerprint"])
    events = []
    seen: dict[tuple[str, date, ActionKind], CorporateAction] = {}
    for index, row in enumerate(payload["events"], 1):
        if not isinstance(row, dict):
            raise ValueError(f"action manifest event {index}: expected an object")
        try:
            event = CorporateAction(
                symbol=str(row["symbol"]).upper(),
                isin=row.get("isin"),
                kind=ActionKind(row["type"]),
                ex_date=_day(row.get("ex_date"), f"events[{index}].ex_date"),
                record_date=_day(
                    row.get("record_date"), f"events[{index}].record_date", optional=True
                ),
                payment_date=_day(
                    row.get("payment_date"), f"events[{index}].payment_date", optional=True
                ),
                payment_timing=_load_payment_timing(row.get("payment_timing")),
                ratio_new_per_old=_decimal(
                    row.get("ratio_new_per_old"), "ratio_new_per_old", optional=True
                ),
                cash_per_share=_decimal(row.get("cash_per_share"), "cash_per_share", optional=True),
                currency=row.get("currency"),
                source=str(payload["source"]),
                source_fingerprint=digest,
                retrieved_at=retrieved,
                verification_status=str(row.get("verification_status", "unverified")),
            )
        except (KeyError, ValueError) as exc:
            raise ValueError(f"action manifest event {index}: {exc}") from exc
        key = (event.symbol, event.ex_date, event.kind)
        if not coverage.start <= event.ex_date <= coverage.end:
            raise ValueError(
                f"action manifest event {index}: ex_date lies outside declared coverage"
            )
        prior = seen.get(key)
        if prior is not None:
            if prior != event:
                raise ValueError(f"conflicting duplicate corporate action: {key}")
            raise ValueError(f"duplicate corporate action: {key}")
        seen[key] = event
        events.append(event)
    return tuple(sorted(events, key=lambda item: (item.ex_date, item.symbol, item.kind))), coverage


def validate_actions(actions: tuple[CorporateAction, ...] | list[CorporateAction]) -> None:
    seen: dict[tuple[str, date, ActionKind], CorporateAction] = {}
    for action in actions:
        key = (action.symbol, action.ex_date, action.kind)
        if key in seen:
            if seen[key] != action:
                raise ValueError(f"conflicting duplicate corporate action: {key}")
            raise ValueError(f"duplicate corporate action: {key}")
        seen[key] = action


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_quantity(quantity: int, factor: Decimal) -> int:
    """Apply exact share multiplier; block fractional entitlements pending cash-in-lieu terms."""
    result = Decimal(quantity) * factor
    if result != result.to_integral_value():
        raise ValueError(
            "corporate action creates fractional shares; explicit cash-in-lieu terms are required"
        )
    if result <= 0:
        raise ValueError("corporate action produced nonpositive quantity")
    return int(result)


def unsupported_action_reason(action: CorporateAction) -> str | None:
    if action.kind in SUPPORTED_ACTIONS:
        return None
    return f"{action.kind.value} requires event-specific consideration/election handling"
