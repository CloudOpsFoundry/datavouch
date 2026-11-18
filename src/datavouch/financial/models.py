"""Strict financial evidence contracts with exact numeric input."""

import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any

from datavouch.core.configuration import _object
from datavouch.core.models import nonempty
from datavouch.verification.correctness import instant


def amount(value: object, *, signed: bool = False) -> Fraction:
    """Decode bounded decimal strings without binary floating point or ambient precision."""
    if not isinstance(value, str) or not re.fullmatch(r"-?\d{1,18}(?:\.\d{1,12})?", value):
        raise ValueError(
            "Amounts must be decimal strings with at most 18 whole and 12 fractional digits"
        )
    result = Fraction(Decimal(value))
    if not signed and result < 0:
        raise ValueError("Expected a nonnegative amount")
    return result


def currency(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("Currency must be a three-letter uppercase code")


def ids(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError(f"{name} must be an array of at most 1000 IDs")
    for item in value:
        nonempty(item, name)
    if len(set(value)) != len(value):
        raise ValueError(f"Duplicate {name}")
    return tuple(value)


@dataclass(frozen=True, slots=True)
class Usage:
    start: str
    end: str
    execution_ids: tuple[str, ...]
    reference: str | None
    billed_bytes: int | None
    billed_slot_hours: str | None
    consumed_slot_ms: int | None

    @classmethod
    def decode(cls, data: Any) -> Usage:
        value = _object(
            data,
            {"start", "end", "execution_ids"},
            {"reference", "billed_bytes", "billed_slot_hours", "consumed_slot_ms"},
        )
        if instant(value["start"]) >= instant(value["end"]):
            raise ValueError("Usage window must be positive")
        reference = value.get("reference")
        if reference is not None:
            nonempty(reference, "usage reference")
        for field in ("billed_bytes", "consumed_slot_ms"):
            number = value.get(field)
            if number is not None and (type(number) is not int or not 0 <= number <= 2**63 - 1):
                raise ValueError("Usage quantities must be nonnegative INT64 values")
        hours = value.get("billed_slot_hours")
        if hours is not None:
            amount(hours)
        return cls(
            value["start"],
            value["end"],
            ids(value["execution_ids"], "execution IDs"),
            reference,
            value.get("billed_bytes"),
            hours,
            value.get("consumed_slot_ms"),
        )


@dataclass(frozen=True, slots=True)
class Pricing:
    model: str
    currency: str
    rate: str | None
    reference: str | None
    valid_from: str | None
    valid_to: str | None

    @classmethod
    def decode(cls, data: Any) -> Pricing:
        value = _object(
            data, {"model", "currency"}, {"rate", "reference", "valid_from", "valid_to"}
        )
        if value["model"] not in ("on_demand", "capacity", "unknown"):
            raise ValueError("Unsupported pricing model")
        currency(value["currency"])
        if value.get("rate") is not None:
            amount(value["rate"])
        if value.get("reference") is not None:
            nonempty(value["reference"], "pricing reference")
        for field in ("valid_from", "valid_to"):
            if value.get(field) is not None:
                instant(value[field])
        if (
            value.get("valid_from")
            and value.get("valid_to")
            and instant(value["valid_from"]) >= instant(value["valid_to"])
        ):
            raise ValueError("Pricing validity window must be positive")
        return cls(
            value["model"],
            value["currency"],
            value.get("rate"),
            value.get("reference"),
            value.get("valid_from"),
            value.get("valid_to"),
        )


@dataclass(frozen=True, slots=True)
class Billing:
    scope: str
    start: str
    end: str
    currency: str
    net_cost: str
    reference: str
    evidence_ids: tuple[str, ...]
    complete: bool

    @classmethod
    def decode(cls, data: Any) -> Billing:
        value = _object(
            data,
            {
                "scope",
                "start",
                "end",
                "currency",
                "net_cost",
                "reference",
                "evidence_ids",
                "complete",
            },
        )
        if instant(value["start"]) >= instant(value["end"]):
            raise ValueError("Billing window must be positive")
        nonempty(value["scope"], "billing scope")
        currency(value["currency"])
        amount(value["net_cost"], signed=True)
        nonempty(value["reference"], "billing reference")
        if type(value["complete"]) is not bool:
            raise ValueError("Billing completeness must be a boolean")
        evidence = ids(value["evidence_ids"], "billing evidence IDs")
        return cls(
            value["scope"],
            value["start"],
            value["end"],
            value["currency"],
            value["net_cost"],
            value["reference"],
            evidence,
            value["complete"],
        )


@dataclass(frozen=True, slots=True)
class Claim:
    id: str
    scope: str
    start: str
    end: str
    evidence_ids: tuple[str, ...]

    @classmethod
    def decode(cls, data: Any) -> Claim:
        value = _object(data, {"id", "scope", "start", "end", "evidence_ids"})
        nonempty(value["id"], "claim ID")
        nonempty(value["scope"], "billing scope")
        if instant(value["start"]) >= instant(value["end"]):
            raise ValueError("Claim window must be positive")
        return cls(
            value["id"],
            value["scope"],
            value["start"],
            value["end"],
            ids(value["evidence_ids"], "claim evidence IDs"),
        )


def overlap(left: Claim, right: Claim) -> bool:
    """Conservatively flag shared evidence or intersecting windows on the same billing pool."""
    return (
        left.id == right.id
        or bool(set(left.evidence_ids) & set(right.evidence_ids))
        or (
            left.scope == right.scope
            and instant(left.start) < instant(right.end)
            and instant(right.start) < instant(left.end)
        )
    )
