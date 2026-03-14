import pandas as pd
import pytest
import xraydb
from periodictable.xsf import xray_sld

from mouse_logbook.adapters.project_xlsx import ProjectInfo, Sample, SampleComponent
from mouse_logbook.models import EnrichedLogbookEntry, LogbookEntry
from mouse_logbook.sample_metadata import SampleMetadataBuilder, SampleMetadataEnricher
from mouse_logbook.sample_metadata_chemistry import (
    ChemistryValidatedComponent,
    ChemistryValidatedSample,
    ParsedChemicalFormula,
    SampleMetadataChemistryValidator,
)
from mouse_logbook.sample_metadata_xray import (
    STANDARD_XRAY_ENERGIES_KEV,
    PeriodictableXrayBackend,
    SampleMetadataXrayCalculator,
)


class FakeChemistryInterpreter:
    def parse_formula(self, formula_text: str) -> ParsedChemicalFormula:
        return ParsedChemicalFormula(
            original_input=formula_text,
            normalized_formula=formula_text,
            atom_counts={"X": 1.0},
        )


class FakeXrayBackend:
    def calculate_component(self, *, formula_text: str, density: float, energy_kev: float):
        scale = 10.0 if formula_text == "H2O" else 20.0
        mu = scale * density * energy_kev
        sld_real = scale * energy_kev
        sld_imag = density * energy_kev
        return mu, sld_real, sld_imag


def _chemistry_project_with_volume_fractions():
    parsed_project = ProjectInfo(
        proposal_id="2025001",
        name="Project",
        email="a@b.de",
        organisation="Org",
        title="Title",
        description="Description",
        samples={
            1: Sample(
                sample_id=1,
                sample_name="S1",
                composition="H2O, SiO2",
                components=(
                    SampleComponent(component_id="c1", composition="H2O", density=1.0, vol_frac=0.25),
                    SampleComponent(component_id="c2", composition="SiO2", density=2.0, vol_frac=0.75),
                ),
            )
        },
    )
    metadata_project = SampleMetadataBuilder().build_project(parsed_project).value
    return SampleMetadataChemistryValidator(interpreter=FakeChemistryInterpreter()).validate_project(metadata_project).value


def _chemistry_project_with_mass_fractions():
    parsed_project = ProjectInfo(
        proposal_id="2025001",
        name="Project",
        email="a@b.de",
        organisation="Org",
        title="Title",
        description="Description",
        samples={
            1: Sample(
                sample_id=1,
                sample_name="S1",
                composition="H2O, SiO2",
                components=(
                    SampleComponent(component_id="c1", composition="H2O", density=1.0, mass_frac=0.25),
                    SampleComponent(component_id="c2", composition="SiO2", density=2.0, mass_frac=0.75),
                ),
            )
        },
    )
    metadata_project = SampleMetadataBuilder().build_project(parsed_project).value
    return SampleMetadataChemistryValidator(interpreter=FakeChemistryInterpreter()).validate_project(metadata_project).value


def test_sample_metadata_xray_calculator_precomputes_cu_and_mo() -> None:
    chemistry_project = _chemistry_project_with_volume_fractions()

    report = SampleMetadataXrayCalculator(backend=FakeXrayBackend()).precompute_project(chemistry_project)

    assert not report.has_errors
    xray_project = report.value
    sample = xray_project.samples[1]
    assert set(sample.standard_xray) == set(STANDARD_XRAY_ENERGIES_KEV)
    cu = sample.standard_xray["cu_ka"]
    mo = sample.standard_xray["mo_ka"]
    assert cu.energy_kev == 8.04
    assert mo.energy_kev == 17.4
    assert cu.phase_properties["c1"].absorption_coefficient_m_inv == pytest.approx(80.4)
    assert cu.phase_properties["c2"].absorption_coefficient_m_inv == pytest.approx(321.6)
    assert cu.overall_absorption_coefficient_m_inv == pytest.approx(0.25 * 80.4 + 0.75 * 321.6)
    assert cu.volume_fraction_source == "volume_fraction"


def test_sample_metadata_xray_calculator_exposes_arbitrary_energy_methods() -> None:
    chemistry_project = _chemistry_project_with_volume_fractions()
    sample = chemistry_project.samples[1]

    report = SampleMetadataXrayCalculator(backend=FakeXrayBackend()).calculate_sample_at_energy(sample, energy_kev=12.0)

    assert not report.has_errors
    props = report.value
    assert props.energy_kev == 12.0
    assert props.phase_properties["c1"].scattering_length_density.real_m_inv2 == pytest.approx(120.0)
    assert props.phase_properties["c2"].absorption_coefficient_m_inv == pytest.approx(480.0)


def test_sample_metadata_xray_calculator_derives_overall_absorption_from_mass_fractions() -> None:
    chemistry_project = _chemistry_project_with_mass_fractions()
    sample = chemistry_project.samples[1]

    report = SampleMetadataXrayCalculator(backend=FakeXrayBackend()).calculate_sample_at_energy(sample, energy_kev=8.04)

    assert not report.has_errors
    props = report.value
    expected_vf_c1 = (0.25 / 1.0) / ((0.25 / 1.0) + (0.75 / 2.0))
    expected_vf_c2 = (0.75 / 2.0) / ((0.25 / 1.0) + (0.75 / 2.0))
    assert props.volume_fraction_source == "derived_from_mass_fraction"
    assert props.volume_fractions == {"c1": expected_vf_c1, "c2": expected_vf_c2}
    expected_mu = expected_vf_c1 * 80.4 + expected_vf_c2 * 321.6
    assert props.overall_absorption_coefficient_m_inv == pytest.approx(expected_mu)


def test_sample_metadata_xray_calculator_reports_missing_density_for_component() -> None:
    parsed_project = ProjectInfo(
        proposal_id="2025001",
        name="Project",
        email="a@b.de",
        organisation="Org",
        title="Title",
        description="Description",
        samples={
            1: Sample(
                sample_id=1,
                sample_name="S1",
                composition="H2O",
                components=(SampleComponent(component_id="c1", composition="H2O", density=None, vol_frac=1.0),),
            )
        },
    )
    chemistry_project = SampleMetadataChemistryValidator(interpreter=FakeChemistryInterpreter()).validate_project(
        SampleMetadataBuilder().build_project(parsed_project).value
    ).value

    report = SampleMetadataXrayCalculator(backend=FakeXrayBackend()).calculate_sample_at_energy(
        chemistry_project.samples[1], energy_kev=8.04
    )

    assert report.has_errors
    assert any("component 'c1' is missing density required for X-ray properties" in str(issue) for issue in report.issues)
    assert report.value.phase_properties == {}
    assert report.value.overall_absorption_coefficient_m_inv is None


def test_sample_metadata_xray_calculator_warns_when_overall_absorption_cannot_be_derived() -> None:
    parsed_project = ProjectInfo(
        proposal_id="2025001",
        name="Project",
        email="a@b.de",
        organisation="Org",
        title="Title",
        description="Description",
        samples={
            1: Sample(
                sample_id=1,
                sample_name="S1",
                composition="H2O, SiO2",
                components=(
                    SampleComponent(component_id="c1", composition="H2O", density=1.0),
                    SampleComponent(component_id="c2", composition="SiO2", density=2.0),
                ),
            )
        },
    )
    chemistry_project = SampleMetadataChemistryValidator(interpreter=FakeChemistryInterpreter()).validate_project(
        SampleMetadataBuilder().build_project(parsed_project).value
    ).value

    report = SampleMetadataXrayCalculator(backend=FakeXrayBackend()).calculate_sample_at_energy(
        chemistry_project.samples[1], energy_kev=8.04
    )

    assert not report.has_errors
    assert report.value.phase_properties["c1"].absorption_coefficient_m_inv == pytest.approx(80.4)
    assert report.value.overall_absorption_coefficient_m_inv is None
    assert report.value.volume_fraction_source == "unavailable"
    assert any(
        "overall absorption unavailable because neither volume_fraction nor mass_fraction is available" in str(issue)
        for issue in report.issues
    )


def test_sample_metadata_xray_calculator_reports_missing_formula_for_component() -> None:
    sample = ChemistryValidatedSample(
        sample_id=1,
        sample_name="S1",
        composition_summary="H2O",
        components=(
            ChemistryValidatedComponent(
                component_id="c1",
                composition="H2O",
                density=1.0,
                volume_fraction=1.0,
                formula=None,
            ),
        ),
    )

    report = SampleMetadataXrayCalculator(backend=FakeXrayBackend()).calculate_sample_at_energy(sample, energy_kev=8.04)

    assert report.has_errors
    assert any(
        "component 'c1' is missing parsed chemistry formula required for X-ray properties" in str(issue)
        for issue in report.issues
    )
    assert report.value.phase_properties == {}
    assert report.value.overall_absorption_coefficient_m_inv is None


def test_sample_metadata_xray_calculator_wraps_enriched_entry() -> None:
    parsed_project = ProjectInfo(
        proposal_id="2025001",
        name="Project",
        email="a@b.de",
        organisation="Org",
        title="Title",
        description="Description",
        samples={
            1: Sample(
                sample_id=1,
                sample_name="S1",
                composition="H2O",
                components=(SampleComponent(component_id="c1", composition="H2O", density=1.0, vol_frac=1.0),),
            )
        },
    )
    metadata_enriched = SampleMetadataEnricher().enrich_one(
        EnrichedLogbookEntry(
            entry=LogbookEntry(
                row_index=0,
                convert_to_script=True,
                date=pd.Timestamp("2026-03-03"),
                proposal_id="2025001",
                sample_id=1,
                user="user",
                batch_num=1,
                sample_position_id="P1",
                matrix_fraction=0.5,
                sample_thickness=1.2,
                protocol="prot",
                additional_parameters={},
            ),
            project=parsed_project,
            sample=parsed_project.samples[1],
            sample_position={"motor_a": 1.5},
        )
    ).value
    chemistry_enriched = SampleMetadataChemistryValidator(interpreter=FakeChemistryInterpreter()).validate_enriched_entry(
        metadata_enriched
    ).value

    report = SampleMetadataXrayCalculator(backend=FakeXrayBackend()).precompute_enriched_entry(chemistry_enriched)

    assert not report.has_errors
    assert report.value.sample.standard_xray["cu_ka"].overall_absorption_coefficient_m_inv == pytest.approx(80.4)
    assert report.value.sample_position == {"motor_a": 1.5}


def test_periodictable_xray_backend_matches_library_units() -> None:
    mu_m_inv, sld_real_m_inv2, sld_imag_m_inv2 = PeriodictableXrayBackend().calculate_component(
        formula_text="H2O",
        density=1.0,
        energy_kev=8.04,
    )

    expected_mu_m_inv = float(xraydb.material_mu("H2O", density=1.0, energy=8040.0)) * 100.0
    expected_sld_real, expected_sld_imag = xray_sld("H2O", density=1.0, energy=8.04)

    assert mu_m_inv == pytest.approx(expected_mu_m_inv)
    assert sld_real_m_inv2 == pytest.approx(float(expected_sld_real) * 1e14)
    assert sld_imag_m_inv2 == pytest.approx(float(expected_sld_imag) * 1e14)
