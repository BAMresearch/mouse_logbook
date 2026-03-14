import pandas as pd
import pytest

from mouse_logbook.models import LogbookEntry
from mouse_logbook.sample_metadata_chemistry import (
    ChemistryValidatedComponent,
    ChemistryValidatedEnrichedLogbookEntry,
    ChemistryValidatedProject,
    ChemistryValidatedSample,
    ParsedChemicalFormula,
)
from mouse_logbook.sample_metadata_materials import (
    PeriodictableMaterialInterpreter,
    SampleMetadataMaterialsCalculator,
)


def _formula(formula_text: str, atom_counts: dict[str, float]) -> ParsedChemicalFormula:
    return ParsedChemicalFormula(
        original_input=formula_text,
        normalized_formula=formula_text,
        atom_counts=atom_counts,
    )


def _sample_with_volume_fractions() -> ChemistryValidatedSample:
    return ChemistryValidatedSample(
        sample_id=1,
        sample_name="S1",
        composition_summary="H2O, SiO2",
        components=(
            ChemistryValidatedComponent(
                component_id="c1",
                composition="H2O",
                density=1.0,
                volume_fraction=0.25,
                formula=_formula("H2O", {"H": 2.0, "O": 1.0}),
            ),
            ChemistryValidatedComponent(
                component_id="c2",
                composition="SiO2",
                density=2.0,
                volume_fraction=0.75,
                formula=_formula("SiO2", {"Si": 1.0, "O": 2.0}),
            ),
        ),
    )


def _sample_with_mass_fractions(*, include_density: bool = True) -> ChemistryValidatedSample:
    return ChemistryValidatedSample(
        sample_id=1,
        sample_name="S1",
        composition_summary="H2O, SiO2",
        components=(
            ChemistryValidatedComponent(
                component_id="c1",
                composition="H2O",
                density=1.0 if include_density else None,
                mass_fraction=0.25,
                formula=_formula("H2O", {"H": 2.0, "O": 1.0}),
            ),
            ChemistryValidatedComponent(
                component_id="c2",
                composition="SiO2",
                density=2.0 if include_density else None,
                mass_fraction=0.75,
                formula=_formula("SiO2", {"Si": 1.0, "O": 2.0}),
            ),
        ),
    )


def test_periodictable_material_interpreter_characterizes_formula() -> None:
    report = SampleMetadataMaterialsCalculator(
        interpreter=PeriodictableMaterialInterpreter()
    ).characterize_component(
        ChemistryValidatedComponent(
            component_id="c1",
            composition="H2O",
            density=0.998,
            formula=_formula("H2O", {"H": 2.0, "O": 1.0}),
        )
    )

    assert not report.has_errors
    component = report.value
    assert component.density.value_g_cm3 == pytest.approx(0.998)
    assert component.density.kind == "true_density"
    assert component.density.provenance == "experimentally_determined"
    assert component.formula_properties.molar_mass_g_mol == pytest.approx(18.015)
    assert component.formula_properties.element_mass_fractions == pytest.approx(
        {"H": 0.11190674437968359, "O": 0.8880932556203164}
    )
    assert component.formula_properties.element_atom_fractions == pytest.approx(
        {"H": 2.0 / 3.0, "O": 1.0 / 3.0}
    )


def test_materials_calculator_derives_apparent_density_from_volume_fractions() -> None:
    report = SampleMetadataMaterialsCalculator().estimate_sample(_sample_with_volume_fractions())

    assert not report.has_errors
    sample = report.value
    assert sample.sample_density.value_g_cm3 == pytest.approx(1.75)
    assert sample.sample_density.kind == "apparent_density"
    assert sample.sample_density.provenance == "estimated_from_volume_fraction"
    assert sample.phase_volume_fractions == {"c1": 0.25, "c2": 0.75}
    assert sample.phase_volume_fraction_provenance == "experimentally_determined"
    assert sample.phase_mass_fractions == pytest.approx({"c1": 1.0 / 7.0, "c2": 6.0 / 7.0})
    assert sample.phase_mass_fraction_provenance == "estimated_from_volume_fraction"
    assert sample.composition.provenance == "estimated_from_volume_fraction"
    assert sample.composition.element_mass_fractions == pytest.approx(
        {"H": 0.015986677768526228, "O": 0.5833529979577809, "Si": 0.4006603242736921}
    )
    assert sample.composition.element_atom_fractions == pytest.approx(
        {"H": 0.2381793351687449, "O": 0.5475769990822943, "Si": 0.2142436657489609}
    )


def test_materials_calculator_derives_apparent_density_from_mass_fractions() -> None:
    report = SampleMetadataMaterialsCalculator().estimate_sample(_sample_with_mass_fractions())

    assert not report.has_errors
    sample = report.value
    assert sample.sample_density.value_g_cm3 == pytest.approx(1.6)
    assert sample.sample_density.kind == "apparent_density"
    assert sample.sample_density.provenance == "estimated_from_mass_fraction"
    assert sample.phase_mass_fractions == {"c1": 0.25, "c2": 0.75}
    assert sample.phase_mass_fraction_provenance == "experimentally_determined"
    assert sample.phase_volume_fractions == pytest.approx({"c1": 0.4, "c2": 0.6})
    assert sample.phase_volume_fraction_provenance == "estimated_from_mass_fraction"
    assert sample.composition.provenance == "estimated_from_mass_fraction"
    assert sample.composition.element_mass_fractions == pytest.approx(
        {"H": 0.027976686094920897, "O": 0.6214457219945811, "Si": 0.3505775919104983}
    )
    assert sample.composition.element_atom_fractions == pytest.approx(
        {"H": 0.3509685032010842, "O": 0.4911824150661246, "Si": 0.15784908173279127}
    )


def test_materials_calculator_can_derive_composition_without_density_when_mass_fractions_exist() -> None:
    report = SampleMetadataMaterialsCalculator().estimate_sample(_sample_with_mass_fractions(include_density=False))

    assert not report.has_errors
    sample = report.value
    assert sample.sample_density.value_g_cm3 is None
    assert sample.sample_density.kind is None
    assert sample.sample_density.provenance == "unavailable"
    assert sample.phase_mass_fractions == {"c1": 0.25, "c2": 0.75}
    assert sample.phase_mass_fraction_provenance == "experimentally_determined"
    assert sample.composition.provenance == "estimated_from_mass_fraction"
    assert sample.composition.element_mass_fractions == pytest.approx(
        {"H": 0.027976686094920897, "O": 0.6214457219945811, "Si": 0.3505775919104983}
    )
    assert any("sample density unavailable" in str(issue) for issue in report.issues)


def test_materials_calculator_reports_unavailable_results_without_phase_fractions() -> None:
    sample = ChemistryValidatedSample(
        sample_id=1,
        sample_name="S1",
        composition_summary="H2O",
        components=(
            ChemistryValidatedComponent(
                component_id="c1",
                composition="H2O",
                density=1.0,
                formula=_formula("H2O", {"H": 2.0, "O": 1.0}),
            ),
        ),
    )

    report = SampleMetadataMaterialsCalculator().estimate_sample(sample)

    assert not report.has_errors
    assert report.value.sample_density.provenance == "unavailable"
    assert report.value.composition.provenance == "unavailable"
    assert any("phase mass fractions unavailable" in str(issue) for issue in report.issues)


def test_materials_calculator_wraps_enriched_entry() -> None:
    sample = _sample_with_volume_fractions()
    project = ChemistryValidatedProject(
        proposal_id="2025001",
        name="Project",
        email="a@b.de",
        organisation="Org",
        title="Title",
        description="Description",
        samples={1: sample},
    )
    enriched = ChemistryValidatedEnrichedLogbookEntry(
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
        project=project,
        sample=sample,
        sample_position={"motor_a": 1.5},
    )

    report = SampleMetadataMaterialsCalculator().estimate_enriched_entry(enriched)

    assert not report.has_errors
    assert report.value.sample.sample_density.value_g_cm3 == pytest.approx(1.75)
    assert report.value.sample_position == {"motor_a": 1.5}
