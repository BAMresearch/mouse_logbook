import pytest

from mouse_logbook.units import (
    absorption_coefficient_cm_inv_to_m_inv,
    absorption_coefficient_m_inv_to_cm_inv,
    energy_kev_to_ev,
    sld_m_inv2_to_micro_inverse_angstrom_sq,
    sld_micro_inverse_angstrom_sq_to_m_inv2,
)


def test_energy_kev_to_ev() -> None:
    assert energy_kev_to_ev(8.04) == pytest.approx(8040.0)
    assert energy_kev_to_ev(17.4) == pytest.approx(17400.0)


def test_absorption_coefficient_cm_inv_to_m_inv() -> None:
    assert absorption_coefficient_cm_inv_to_m_inv(1.0) == pytest.approx(100.0)
    assert absorption_coefficient_cm_inv_to_m_inv(10.219046663824201) == pytest.approx(1021.90466638242)


def test_absorption_coefficient_m_inv_to_cm_inv() -> None:
    assert absorption_coefficient_m_inv_to_cm_inv(100.0) == pytest.approx(1.0)
    assert absorption_coefficient_m_inv_to_cm_inv(1021.90466638242) == pytest.approx(10.219046663824201)


def test_sld_micro_inverse_angstrom_sq_to_m_inv2() -> None:
    assert sld_micro_inverse_angstrom_sq_to_m_inv2(1.0) == pytest.approx(1e14)
    assert sld_micro_inverse_angstrom_sq_to_m_inv2(9.469284322613177) == pytest.approx(9.469284322613177e14)


def test_sld_m_inv2_to_micro_inverse_angstrom_sq() -> None:
    assert sld_m_inv2_to_micro_inverse_angstrom_sq(1e14) == pytest.approx(1.0)
    assert sld_m_inv2_to_micro_inverse_angstrom_sq(9.469284322613177e14) == pytest.approx(9.469284322613177)
