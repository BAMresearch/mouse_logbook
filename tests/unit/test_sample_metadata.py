import pandas as pd

from mouse_logbook.adapters.project_xlsx import ProjectInfo, Sample, SampleComponent
from mouse_logbook.models import EnrichedLogbookEntry, LogbookEntry
from mouse_logbook.sample_metadata import (
    SampleMetadataBuilder,
    SampleMetadataEnrichedLogbookEntry,
    SampleMetadataEnricher,
)


def _project_with_samples(*, components: tuple[SampleComponent, ...]) -> ProjectInfo:
    sample = Sample(sample_id=1, sample_name="S1", composition="H2O, SiO2", components=components)
    return ProjectInfo(
        proposal_id="2025001",
        name="Project",
        email="a@b.de",
        organisation="Org",
        title="Title",
        description="Description",
        samples={1: sample},
    )


def test_sample_metadata_builder_maps_project_samples() -> None:
    project = _project_with_samples(
        components=(
            SampleComponent(component_id="c1", composition="H2O", density=1.0, vol_frac=0.25, component_name="Water"),
            SampleComponent(component_id="c2", composition="SiO2", density=2.2, vol_frac=0.75),
        )
    )

    report = SampleMetadataBuilder().build_project(project)

    assert not report.has_errors
    metadata_project = report.value
    metadata_sample = metadata_project.samples[1]
    assert metadata_project.proposal_id == "2025001"
    assert metadata_sample.sample_name == "S1"
    assert [component.component_id for component in metadata_sample.components] == ["c1", "c2"]
    assert metadata_sample.components[0].component_name == "Water"
    assert metadata_sample.components[1].density == 2.2


def test_sample_metadata_builder_reports_duplicate_component_ids() -> None:
    project = _project_with_samples(
        components=(
            SampleComponent(component_id="dup", composition="H2O", density=1.0),
            SampleComponent(component_id="dup", composition="D2O", density=1.1),
        )
    )

    report = SampleMetadataBuilder().build_project(project)

    assert report.has_errors
    assert any("duplicate component_id 'dup'" in str(issue) for issue in report.issues)
    assert len(report.value.samples[1].components) == 2


def test_sample_metadata_enricher_wraps_core_enriched_entry() -> None:
    project = _project_with_samples(
        components=(
            SampleComponent(component_id="c1", composition="H2O", density=1.0, vol_frac=1.0),
        )
    )
    entry = LogbookEntry(
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
    )
    enriched = EnrichedLogbookEntry(
        entry=entry,
        project=project,
        sample=project.samples[1],
        sample_position={"motor_a": 1.5},
    )

    report = SampleMetadataEnricher().enrich_one(enriched)

    assert not report.has_errors
    metadata_entry = report.value
    assert isinstance(metadata_entry, SampleMetadataEnrichedLogbookEntry)
    assert metadata_entry.entry == entry
    assert metadata_entry.project.proposal_id == "2025001"
    assert metadata_entry.sample.sample_id == 1
    assert metadata_entry.sample_position == {"motor_a": 1.5}


def test_sample_metadata_enricher_reports_missing_sample_in_project() -> None:
    project = ProjectInfo(
        proposal_id="2025001",
        name="Project",
        email="a@b.de",
        organisation="Org",
        title="Title",
        description="Description",
        samples={},
    )
    orphan_sample = Sample(
        sample_id=7,
        sample_name="Orphan",
        composition="H2O",
        components=(SampleComponent(component_id="c1", composition="H2O", density=1.0),),
    )
    entry = LogbookEntry(
        row_index=0,
        convert_to_script=True,
        date=pd.Timestamp("2026-03-03"),
        proposal_id="2025001",
        sample_id=7,
        user="user",
        batch_num=1,
        sample_position_id="P1",
        matrix_fraction=0.5,
        sample_thickness=1.2,
        protocol="prot",
        additional_parameters={},
    )
    enriched = EnrichedLogbookEntry(
        entry=entry,
        project=project,
        sample=orphan_sample,
        sample_position={"motor_a": 1.5},
    )

    report = SampleMetadataEnricher().enrich_one(enriched)

    assert report.has_errors
    assert any("sampleId=7 missing from metadata project" in str(issue) for issue in report.issues)
    assert report.value.sample.sample_id == 7


def test_sample_metadata_enricher_enrich_many_collects_values_and_issues() -> None:
    project = _project_with_samples(
        components=(
            SampleComponent(component_id="dup", composition="H2O", density=1.0),
            SampleComponent(component_id="dup", composition="D2O", density=1.1),
        )
    )
    entry = LogbookEntry(
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
    )
    enriched = EnrichedLogbookEntry(
        entry=entry,
        project=project,
        sample=project.samples[1],
        sample_position={"motor_a": 1.5},
    )

    report = SampleMetadataEnricher().enrich_many([enriched])

    assert len(report.value) == 1
    assert report.has_errors
    assert any("duplicate component_id 'dup'" in str(issue) for issue in report.issues)
