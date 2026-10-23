"""Versioned, evidence-aware local transaction-cost schedules.

This module is an offline arithmetic engine. It has no broker client and cannot submit
orders. Source-backed partial schedules fail closed; synthetic rates are opt-in tests.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

D = Decimal
CENT = D("0.01")
SIDES = {"BUY", "SELL"}
STATUSES = {"verified", "partially_verified", "unverified", "synthetic_test_only"}
CATEGORIES = {"statutory", "exchange", "broker", "depository", "tax"}
BASIS = {"notional", "fixed", "component_sum"}
AGGREGATION = {"per_fill", "per_order", "per_day_symbol", "per_settlement_symbol"}
ROUNDING = {"half_up_paise", "unverified"}
GST_TREATMENT = {"taxable", "not_taxable", "separately_modelled", "unresolved"}


class CostProfileError(ValueError):
    """Cost profile is malformed, ambiguous or cannot support the requested quote."""


class CostCoverageError(CostProfileError):
    """No fully supported cost rule covers a transaction date and side."""


def _date(raw: Any, field: str) -> date | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise CostProfileError(f"{field} must be an ISO date or null")
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise CostProfileError(f"{field} has invalid date {raw!r}") from exc
    if parsed.isoformat() != raw:
        raise CostProfileError(f"{field} must use YYYY-MM-DD")
    return parsed


def _decimal(raw: Any, field: str, *, optional: bool = False) -> Decimal | None:
    if raw is None and optional:
        return None
    try:
        value = D(str(raw))
    except (InvalidOperation, ValueError) as exc:
        raise CostProfileError(f"{field} must be a decimal") from exc
    if not value.is_finite() or value < 0:
        raise CostProfileError(f"{field} must be finite and nonnegative")
    return value


@dataclass(frozen=True, slots=True)
class CostRule:
    component: str
    category: str
    basis: str
    aggregation: str
    sides: tuple[str, ...]
    verification_status: str
    rounding: str
    effective_from: date | None = None
    effective_to: date | None = None
    rate: Decimal | None = None
    fixed_amount: Decimal | None = None
    taxable_components: tuple[str, ...] = ()
    source_id: str | None = None
    note: str = ""
    minimum_amount: Decimal | None = None
    cap_amount: Decimal | None = None
    gst_treatment: str = "unresolved"

    def __post_init__(self) -> None:
        if not self.component.strip():
            raise CostProfileError("cost component name is required")
        if self.category not in CATEGORIES:
            raise CostProfileError(f"unsupported cost category {self.category!r}")
        if self.basis not in BASIS or self.aggregation not in AGGREGATION:
            raise CostProfileError("unsupported cost basis or aggregation")
        if self.verification_status not in STATUSES:
            raise CostProfileError("unsupported cost verification status")
        if self.rounding not in ROUNDING:
            raise CostProfileError("unsupported cost rounding policy")
        if self.gst_treatment not in GST_TREATMENT:
            raise CostProfileError("unsupported GST treatment")
        if not self.sides or any(side not in SIDES for side in self.sides):
            raise CostProfileError("cost rule requires BUY and/or SELL sides")
        if len(self.sides) != len(set(self.sides)):
            raise CostProfileError("cost rule sides cannot contain duplicates")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise CostProfileError("effective_to precedes effective_from")
        if self.basis == "notional" and (self.rate is None or self.fixed_amount is not None):
            raise CostProfileError("notional cost rule requires only a rate")
        if self.basis == "fixed" and (self.fixed_amount is None or self.rate is not None):
            raise CostProfileError("fixed cost rule requires only a fixed_amount")
        if self.basis == "component_sum":
            if self.rate is None or not self.taxable_components or self.fixed_amount is not None:
                raise CostProfileError("component_sum rule requires a rate and taxable_components")
            if self.component in self.taxable_components:
                raise CostProfileError("tax component cannot tax itself")
        elif self.taxable_components:
            raise CostProfileError("taxable_components is only valid for component_sum")
        for field_name, value in (
            ("rate", self.rate),
            ("fixed_amount", self.fixed_amount),
            ("minimum_amount", self.minimum_amount),
            ("cap_amount", self.cap_amount),
        ):
            if value is not None and (
                not isinstance(value, Decimal) or not value.is_finite() or value < 0
            ):
                raise CostProfileError(f"{field_name} must be finite and nonnegative")
        if self.rate is not None and self.rate > 1:
            raise CostProfileError("cost rate must be a fraction no greater than one")
        if self.minimum_amount is not None and self.minimum_amount < 0:
            raise CostProfileError("minimum_amount cannot be negative")
        if self.cap_amount is not None and self.cap_amount < 0:
            raise CostProfileError("cap_amount cannot be negative")
        if (
            self.minimum_amount is not None
            and self.cap_amount is not None
            and self.cap_amount < self.minimum_amount
        ):
            raise CostProfileError("cap_amount cannot be less than minimum_amount")


@dataclass(frozen=True, slots=True)
class CostTransaction:
    transaction_id: str
    session_date: date
    symbol: str
    side: str
    notional: Decimal
    quantity: int
    order_id: str | None = None
    settlement_id: str | None = None

    def __post_init__(self) -> None:
        if not self.transaction_id or not self.symbol.strip():
            raise CostProfileError("transaction_id and symbol are required")
        if not isinstance(self.session_date, date):
            raise CostProfileError("session_date must be a date")
        if self.side not in SIDES:
            raise CostProfileError("transaction side must be BUY or SELL")
        if not isinstance(self.notional, Decimal) or not self.notional.is_finite():
            raise CostProfileError("notional must be a finite Decimal")
        if (
            self.notional <= 0
            or not isinstance(self.quantity, int)
            or isinstance(self.quantity, bool)
            or self.quantity <= 0
        ):
            raise CostProfileError("notional and quantity must be positive")


@dataclass(frozen=True, slots=True)
class CostLine:
    component: str
    category: str
    transaction_ids: tuple[str, ...]
    aggregation_key: str
    basis: str
    amount: Decimal
    source_id: str | None


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    profile_version: str
    lines: tuple[CostLine, ...]

    @property
    def total(self) -> Decimal:
        return sum((line.amount for line in self.lines), D(0))

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_version": self.profile_version,
            "total": str(self.total),
            "lines": [
                {
                    "component": line.component,
                    "category": line.category,
                    "transaction_ids": list(line.transaction_ids),
                    "aggregation_key": line.aggregation_key,
                    "basis": line.basis,
                    "amount": str(line.amount),
                    "source_id": line.source_id,
                }
                for line in self.lines
            ],
        }


@dataclass(frozen=True, slots=True)
class CostProfile:
    version: str
    market: str
    segment: str
    required_components: tuple[tuple[str, tuple[str, ...]], ...]
    rules: tuple[CostRule, ...]
    status: str
    synthetic: bool = False
    assumptions: tuple[str, ...] = ()
    provenance_manifest: Path | None = None

    def __post_init__(self) -> None:
        if not self.version or not self.market or not self.segment:
            raise CostProfileError("version, market and segment are required")
        if self.status not in {"partial", "complete", "synthetic_test_only"}:
            raise CostProfileError(
                "profile status must be partial, complete or synthetic_test_only"
            )
        if self.synthetic != (self.status == "synthetic_test_only"):
            raise CostProfileError("synthetic profile flag and status disagree")
        if not self.required_components:
            raise CostProfileError("required_components cannot be empty")
        names = [name for name, _ in self.required_components]
        if len(names) != len(set(names)):
            raise CostProfileError("required component names must be unique")
        for name, sides in self.required_components:
            if not name.strip() or not sides or any(side not in SIDES for side in sides):
                raise CostProfileError("required components need a name and valid sides")
        self._validate_intervals()

    def _validate_intervals(self) -> None:
        by_key: dict[tuple[str, str], list[CostRule]] = {}
        for rule in self.rules:
            for side in rule.sides:
                by_key.setdefault((rule.component, side), []).append(rule)
        for key, rules in by_key.items():
            dated = sorted(
                (rule for rule in rules if rule.effective_from is not None),
                key=lambda rule: rule.effective_from,
            )
            for left, right in zip(dated, dated[1:], strict=False):
                if left.effective_to is None or left.effective_to >= right.effective_from:
                    raise CostProfileError(f"overlapping intervals for {key[0]} {key[1]}")

    def _rule_for(self, component: str, side: str, session: date) -> CostRule:
        matching = [
            rule
            for rule in self.rules
            if rule.component == component
            and side in rule.sides
            and rule.effective_from is not None
            and rule.effective_from <= session
            and (rule.effective_to is None or session <= rule.effective_to)
        ]
        if len(matching) != 1:
            raise CostCoverageError(
                f"{component} {side} has no unique effective tariff on {session}"
            )
        rule = matching[0]
        if rule.verification_status not in {"verified", "synthetic_test_only"}:
            raise CostCoverageError(
                f"{component} {side} on {session} is {rule.verification_status}, not applicable"
            )
        if rule.rounding == "unverified":
            raise CostCoverageError(f"rounding for {component} is not verified")
        return rule

    def coverage_errors(self, session: date) -> list[str]:
        errors = []
        for component, sides in self.required_components:
            for side in sides:
                try:
                    self._rule_for(component, side, session)
                except CostProfileError as exc:
                    errors.append(str(exc))
        return errors

    def quote(self, transactions: list[CostTransaction]) -> CostBreakdown:
        """Calculate fully covered costs only; group settlement-level fees once per symbol/day."""
        if not transactions:
            raise CostProfileError("at least one transaction is required")
        ids = [transaction.transaction_id for transaction in transactions]
        if len(ids) != len(set(ids)):
            raise CostProfileError("duplicate transaction_id in cost quote")
        selected: dict[tuple[str, str, date], CostRule] = {}
        for transaction in transactions:
            for component, sides in self.required_components:
                if transaction.side not in sides:
                    continue
                selected[(component, transaction.side, transaction.session_date)] = self._rule_for(
                    component, transaction.side, transaction.session_date
                )
        grouped: dict[tuple[str, str], list[CostTransaction]] = {}
        for transaction in transactions:
            for component, sides in self.required_components:
                if transaction.side not in sides:
                    continue
                rule = selected[(component, transaction.side, transaction.session_date)]
                if rule.aggregation == "per_fill":
                    key = (component, transaction.transaction_id)
                elif rule.aggregation == "per_order":
                    key = (
                        component,
                        f"{transaction.session_date}:{transaction.symbol}:"
                        f"{transaction.order_id or transaction.transaction_id}",
                    )
                else:
                    aggregation_value = (
                        transaction.session_date.isoformat()
                        if rule.aggregation == "per_day_symbol"
                        else f"{transaction.session_date}:{transaction.settlement_id}"
                        if transaction.settlement_id
                        else None
                    )
                    if not aggregation_value:
                        raise CostProfileError(
                            f"{rule.aggregation} rule {component} requires explicit aggregation id"
                        )
                    key = (component, f"{aggregation_value}:{transaction.symbol}")
                grouped.setdefault(key, []).append(transaction)

        amounts_by_tx_component: dict[tuple[str, str], Decimal] = {}
        lines: list[CostLine] = []
        deferred: list[tuple[CostRule, list[CostTransaction], str]] = []
        for (component, aggregation_key), members in grouped.items():
            side = members[0].side
            rule = selected[(component, side, members[0].session_date)]
            if rule.basis == "component_sum":
                deferred.append((rule, members, aggregation_key))
                continue
            raw = (
                sum((item.notional for item in members), D(0)) * (rule.rate or D(0))
                if rule.basis == "notional"
                else rule.fixed_amount or D(0)
            )
            if rule.minimum_amount is not None:
                raw = max(raw, rule.minimum_amount)
            if rule.cap_amount is not None:
                raw = min(raw, rule.cap_amount)
            amount = _round(raw, rule.rounding)
            transaction_ids = tuple(item.transaction_id for item in members)
            line = CostLine(
                component,
                rule.category,
                transaction_ids,
                aggregation_key,
                rule.basis,
                amount,
                rule.source_id,
            )
            lines.append(line)
            for transaction_id in transaction_ids:
                amounts_by_tx_component[(transaction_id, component)] = amounts_by_tx_component.get(
                    (transaction_id, component), D(0)
                ) + amount / len(transaction_ids)
        for rule, members, aggregation_key in deferred:
            transaction_ids = tuple(item.transaction_id for item in members)
            component_sum = sum(
                (
                    amounts_by_tx_component.get((transaction_id, component), D(0))
                    for transaction_id in transaction_ids
                    for component in rule.taxable_components
                ),
                D(0),
            )
            amount = _round(component_sum * (rule.rate or D(0)), rule.rounding)
            lines.append(
                CostLine(
                    rule.component,
                    rule.category,
                    transaction_ids,
                    aggregation_key,
                    "component_sum:" + "+".join(rule.taxable_components),
                    amount,
                    rule.source_id,
                )
            )
        lines.sort(key=lambda item: (item.aggregation_key, item.component))
        return CostBreakdown(self.version, tuple(lines))


def _round(value: Decimal, mode: str) -> Decimal:
    if mode != "half_up_paise":
        raise CostCoverageError("fee rounding is not verified")
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def load_cost_profile(path: Path, *, allow_synthetic: bool = False) -> CostProfile:
    """Load strict JSON profile and reject missing fields and unsupported assumptions."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CostProfileError(f"cannot read cost profile {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CostProfileError("cost profile must be a JSON object")
    required_top = {
        "schema_version",
        "version",
        "market",
        "segment",
        "status",
        "synthetic",
        "required_components",
        "rules",
        "assumptions",
        "provenance_manifest",
    }
    missing = required_top - payload.keys()
    if missing:
        raise CostProfileError("missing profile fields: " + ", ".join(sorted(missing)))
    if payload["schema_version"] != "1.0" or not isinstance(payload["rules"], list):
        raise CostProfileError("cost profile requires schema_version 1.0 and rules array")
    if payload["synthetic"] is True and not allow_synthetic:
        raise CostProfileError("synthetic-only cost profile requires explicit allow_synthetic=True")
    if not isinstance(payload["required_components"], list):
        raise CostProfileError("required_components must be an array")
    requirements = []
    for item in payload["required_components"]:
        if not isinstance(item, dict) or set(item) != {"component", "sides"}:
            raise CostProfileError("each required component requires exactly component and sides")
        requirements.append((str(item["component"]), tuple(item["sides"])))
    rules = tuple(_parse_rule(row, index) for index, row in enumerate(payload["rules"], 1))
    provenance_path = payload["provenance_manifest"]
    provenance = None
    if provenance_path is not None:
        if not isinstance(provenance_path, str):
            raise CostProfileError("provenance_manifest must be a relative path or null")
        provenance_file = (path.parent / provenance_path).resolve()
        try:
            provenance = json.loads(provenance_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CostProfileError(f"cannot read cost provenance manifest: {exc}") from exc
        if not isinstance(provenance, dict) or not isinstance(provenance.get("sources"), list):
            raise CostProfileError("cost provenance manifest requires a sources array")
        source_index = {
            item.get("source_id"): item
            for item in provenance["sources"]
            if isinstance(item, dict) and isinstance(item.get("source_id"), str)
        }
        for rule in rules:
            if rule.verification_status == "verified" and not rule.source_id:
                raise CostProfileError(f"verified rule {rule.component} requires a source_id")
            if rule.source_id and rule.source_id not in source_index:
                raise CostProfileError(
                    f"rule {rule.component} references unknown source {rule.source_id}"
                )
            if rule.verification_status == "verified":
                source = source_index[rule.source_id]
                archive_status = source.get("archive_status", source.get("status"))
                if archive_status != "retrieved_bytes_archived":
                    raise CostProfileError(
                        f"verified rule {rule.component} source bytes are not archived"
                    )
                source_file = (
                    provenance_file.parent / source.get("archive_file", source.get("file", ""))
                ).resolve()
                try:
                    source_bytes = source_file.read_bytes()
                except OSError as exc:
                    raise CostProfileError(f"cannot read verified source {source_file}") from exc
                if hashlib.sha256(source_bytes).hexdigest() != source.get("sha256"):
                    raise CostProfileError(f"source fingerprint mismatch for {rule.source_id}")
    elif any(rule.verification_status == "verified" for rule in rules):
        raise CostProfileError("verified cost rules require provenance_manifest")
    assumptions = payload["assumptions"]
    if not isinstance(assumptions, list) or any(
        not isinstance(value, str) for value in assumptions
    ):
        raise CostProfileError("assumptions must be an array of strings")
    return CostProfile(
        str(payload["version"]),
        str(payload["market"]),
        str(payload["segment"]),
        tuple(requirements),
        rules,
        str(payload["status"]),
        payload["synthetic"],
        tuple(assumptions),
        provenance_file if provenance_path is not None else None,
    )


def _parse_rule(row: Any, index: int) -> CostRule:
    if not isinstance(row, dict):
        raise CostProfileError(f"rule {index} must be an object")
    required = {
        "component",
        "category",
        "basis",
        "aggregation",
        "sides",
        "verification_status",
        "rounding",
        "effective_from",
        "effective_to",
        "source_id",
        "minimum_amount",
        "cap_amount",
        "gst_treatment",
    }
    missing = required - row.keys()
    if missing:
        raise CostProfileError(f"rule {index} missing fields: {', '.join(sorted(missing))}")
    unknown = row.keys() - required - {"rate", "fixed_amount", "taxable_components", "note"}
    if unknown:
        raise CostProfileError(f"rule {index} has unknown fields: {', '.join(sorted(unknown))}")
    return CostRule(
        component=str(row["component"]),
        category=str(row["category"]),
        basis=str(row["basis"]),
        aggregation=str(row["aggregation"]),
        sides=tuple(row["sides"]),
        verification_status=str(row["verification_status"]),
        rounding=str(row["rounding"]),
        effective_from=_date(row["effective_from"], f"rule {index} effective_from"),
        effective_to=_date(row["effective_to"], f"rule {index} effective_to"),
        rate=_decimal(row.get("rate"), f"rule {index} rate", optional=True),
        fixed_amount=_decimal(row.get("fixed_amount"), f"rule {index} fixed_amount", optional=True),
        taxable_components=tuple(row.get("taxable_components", [])),
        source_id=row["source_id"],
        note=str(row.get("note", "")),
        minimum_amount=_decimal(
            row["minimum_amount"], f"rule {index} minimum_amount", optional=True
        ),
        cap_amount=_decimal(row["cap_amount"], f"rule {index} cap_amount", optional=True),
        gst_treatment=str(row["gst_treatment"]),
    )
