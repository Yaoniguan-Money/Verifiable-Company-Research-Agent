"""Normalize extracted fact values for deterministic comparison."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_NUMBER_UNIT_RE = re.compile(
    r"(?P<number>[-+]?\d[\d,]*(?:\.\d+)?)\s*(?P<unit>亿元|万元|千元|万辆|万台|万吨|GWh|MWh|元|亿|万|%|辆|台|吨)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NormalizedFactValue:
    """Comparable representation of a fact value.

    `raw` is still kept in facts/citations. This object is only used to reduce
    false conflicts caused by unit differences in public filings.
    """

    kind: str
    value: Decimal
    unit: str

    @property
    def key(self) -> str:
        return f"{self.kind}:{self._clean_decimal()}:{self.unit}"

    def _clean_decimal(self) -> str:
        return format(self.value.normalize(), "f")


class FactValueNormalizer:
    """Convert common financial-report units into stable comparison keys."""

    _MONEY_FACTORS = {
        "元": Decimal("1"),
        "千元": Decimal("1000"),
        "万元": Decimal("10000"),
        "亿元": Decimal("100000000"),
        "万": Decimal("10000"),
        "亿": Decimal("100000000"),
    }
    _COUNT_FACTORS = {
        "辆": ("vehicle", Decimal("1")),
        "万辆": ("vehicle", Decimal("10000")),
        "台": ("unit", Decimal("1")),
        "万台": ("unit", Decimal("10000")),
        "吨": ("ton", Decimal("1")),
        "万吨": ("ton", Decimal("10000")),
    }
    _ENERGY_FACTORS = {
        "MWh": Decimal("1"),
        "GWh": Decimal("1000"),
    }

    def comparable_key(self, value: str | None) -> str:
        if not value:
            return ""
        normalized = self.normalize(value)
        if normalized is not None:
            return normalized.key
        return self._normalize_raw(value)

    def normalize(self, value: str | None) -> NormalizedFactValue | None:
        if not value:
            return None
        match = _NUMBER_UNIT_RE.search(value.replace(" ", ""))
        if match is None:
            return None

        try:
            number = Decimal(match.group("number").replace(",", ""))
        except InvalidOperation:
            return None

        unit = self._canonical_unit(match.group("unit"))
        if unit in self._MONEY_FACTORS:
            return NormalizedFactValue(
                kind="money",
                value=number * self._MONEY_FACTORS[unit],
                unit="yuan",
            )
        if unit in self._COUNT_FACTORS:
            kind, factor = self._COUNT_FACTORS[unit]
            return NormalizedFactValue(kind=kind, value=number * factor, unit=kind)
        if unit in self._ENERGY_FACTORS:
            return NormalizedFactValue(
                kind="energy",
                value=number * self._ENERGY_FACTORS[unit],
                unit="MWh",
            )
        if unit == "%":
            return NormalizedFactValue(kind="ratio", value=number, unit="percent")
        return None

    def _canonical_unit(self, unit: str) -> str:
        upper = unit.upper()
        if upper in {"GWH", "MWH"}:
            return upper.replace("WH", "Wh")
        return unit

    def _normalize_raw(self, value: str) -> str:
        return value.replace(" ", "").replace(",", "").strip().lower()
