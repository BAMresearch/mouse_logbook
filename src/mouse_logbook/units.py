from __future__ import annotations

from typing import Any

import pint

UNIT_REGISTRY = pint.UnitRegistry()

_KILOELECTRON_VOLT = UNIT_REGISTRY.kiloelectron_volt
_ELECTRON_VOLT = UNIT_REGISTRY.electron_volt
_INVERSE_CENTIMETER = 1 / UNIT_REGISTRY.centimeter
_INVERSE_METER = 1 / UNIT_REGISTRY.meter
_MICRO_INVERSE_ANGSTROM_SQUARED = 1e-6 / (UNIT_REGISTRY.angstrom**2)
_INVERSE_METER_SQUARED = 1 / (UNIT_REGISTRY.meter**2)


def convert_magnitude(value: float, *, source_unit: Any, target_unit: Any) -> float:
    return float((value * source_unit).to(target_unit).magnitude)


def energy_kev_to_ev(value_kev: float) -> float:
    return convert_magnitude(value_kev, source_unit=_KILOELECTRON_VOLT, target_unit=_ELECTRON_VOLT)


def absorption_coefficient_cm_inv_to_m_inv(value_cm_inv: float) -> float:
    return convert_magnitude(value_cm_inv, source_unit=_INVERSE_CENTIMETER, target_unit=_INVERSE_METER)


def absorption_coefficient_m_inv_to_cm_inv(value_m_inv: float) -> float:
    return convert_magnitude(value_m_inv, source_unit=_INVERSE_METER, target_unit=_INVERSE_CENTIMETER)


def sld_micro_inverse_angstrom_sq_to_m_inv2(value_micro_inverse_angstrom_sq: float) -> float:
    return convert_magnitude(
        value_micro_inverse_angstrom_sq,
        source_unit=_MICRO_INVERSE_ANGSTROM_SQUARED,
        target_unit=_INVERSE_METER_SQUARED,
    )


def sld_m_inv2_to_micro_inverse_angstrom_sq(value_m_inv2: float) -> float:
    inverse_angstrom_sq = convert_magnitude(
        value_m_inv2,
        source_unit=_INVERSE_METER_SQUARED,
        target_unit=1 / (UNIT_REGISTRY.angstrom**2),
    )
    return inverse_angstrom_sq * 1e6
