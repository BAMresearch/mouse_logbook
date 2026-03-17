import attrs
import pandas as pd

from mouse_logbook.adapters.project_xlsx import ProjectInfo, Sample, SampleComponent
from mouse_logbook.models import EnrichedLogbookEntry, LogbookEntry
from mouse_logbook.sample_metadata import (
    SampleMetadataBuilder,
    SampleMetadataComponent,
    SampleMetadataEnricher,
    SampleMetadataProject,
    SampleMetadataSample,
)
from mouse_logbook.sample_metadata_chemistry import (
    ParsedChemicalFormula,
    SampleMetadataChemistryValidator,
)


class FakeChemistryInterpreter:
    def parse_formula(self, formula_text: str) -> ParsedChemicalFormula:
        formulas = {
            "H2O": ParsedChemicalFormula(
                original_input="H2O",
                normalized_formula="H2O",
                atom_counts={"H": 2.0, "O": 1.0},
            ),
            "SiO2": ParsedChemicalFormula(
                original_input="SiO2",
                normalized_formula="SiO2",
                atom_counts={"Si": 1.0, "O": 2.0},
            ),
        }
        if formula_text not in formulas:
            raise ValueError(f"Unknown formula {formula_text!r}")
        return formulas[formula_text]


class BrokenChemistryInterpreter:
    def parse_formula(self, formula_text: str) -> ParsedChemicalFormula:
        raise RuntimeError(f"backend unavailable for {formula_text}")


def _sample_metadata_project() -> object:
    project = ProjectInfo(
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
                    SampleComponent(component_id="c2", composition="SiO2", density=2.2, vol_frac=0.75),
                ),
            )
        },
    )
    return SampleMetadataBuilder().build_project(project).value


def test_sample_metadata_chemistry_validator_parses_project_components() -> None:
    metadata_project = _sample_metadata_project()

    report = SampleMetadataChemistryValidator(interpreter=FakeChemistryInterpreter()).validate_project(metadata_project)

    assert not report.has_errors
    validated_sample = report.value.samples[1]
    assert validated_sample.components[0].formula.normalized_formula == "H2O"
    assert validated_sample.components[1].formula.atom_counts == {"Si": 1.0, "O": 2.0}


def test_sample_metadata_chemistry_validator_reports_invalid_formula() -> None:
    metadata_project = _sample_metadata_project()
    bad_component = attrs.evolve(metadata_project.samples[1].components[1], composition="NotChem")
    bad_sample = SampleMetadataSample(
        sample_id=metadata_project.samples[1].sample_id,
        sample_name=metadata_project.samples[1].sample_name,
        composition_summary=metadata_project.samples[1].composition_summary,
        components=(metadata_project.samples[1].components[0], bad_component),
    )
    metadata_project = SampleMetadataProject(
        proposal_id=metadata_project.proposal_id,
        name=metadata_project.name,
        email=metadata_project.email,
        organisation=metadata_project.organisation,
        title=metadata_project.title,
        description=metadata_project.description,
        samples={1: bad_sample},
    )
    report = SampleMetadataChemistryValidator(interpreter=FakeChemistryInterpreter()).validate_project(metadata_project)

    assert report.has_errors
    assert any("component 'c2' has invalid chemistry description 'NotChem'" in str(issue) for issue in report.issues)
    assert report.value.samples[1].components[1].formula is None


def test_sample_metadata_chemistry_validator_reports_missing_chemistry_description() -> None:
    metadata_project = SampleMetadataProject(
        proposal_id="2025001",
        name="Project",
        email="a@b.de",
        organisation="Org",
        title="Title",
        description="Description",
        samples={
            1: SampleMetadataSample(
                sample_id=1,
                sample_name="S1",
                composition_summary="",
                components=(SampleMetadataComponent(component_id="c1", composition="", density=1.0),),
            )
        },
    )

    report = SampleMetadataChemistryValidator(interpreter=FakeChemistryInterpreter()).validate_project(metadata_project)

    assert report.has_errors
    assert any("component 'c1' is missing a chemistry description" in str(issue) for issue in report.issues)
    assert report.value.samples[1].components[0].formula is None


def test_sample_metadata_chemistry_validator_reports_interpreter_failures() -> None:
    metadata_project = _sample_metadata_project()

    report = SampleMetadataChemistryValidator(interpreter=BrokenChemistryInterpreter()).validate_project(metadata_project)

    assert report.has_errors
    assert any("backend unavailable for H2O" in str(issue) for issue in report.issues)
    assert all(component.formula is None for component in report.value.samples[1].components)


def test_sample_metadata_chemistry_validator_wraps_enriched_entry() -> None:
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

    report = SampleMetadataChemistryValidator(interpreter=FakeChemistryInterpreter()).validate_enriched_entry(metadata_enriched)

    assert not report.has_errors
    assert report.value.sample.components[0].formula.normalized_formula == "H2O"
    assert report.value.sample_position == {"motor_a": 1.5}
