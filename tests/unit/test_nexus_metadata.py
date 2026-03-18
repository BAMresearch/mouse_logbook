from pathlib import Path

import attrs
import h5py
import pandas as pd
import pytest

from mouse_logbook.models import LogbookEntry
from mouse_logbook.nexus_metadata import NexusMetadataError, NexusMetadataUpserter
from mouse_logbook.sample_metadata_materials import (
    DensityEstimate,
    MaterialComponent,
    MaterialEnrichedLogbookEntry,
    MaterialProject,
    MaterialSample,
    SampleCompositionEstimate,
)
from mouse_logbook.sample_metadata_xray import (
    PhaseXrayProperties,
    SampleXrayProperties,
    ScatteringLengthDensity,
    XrayEnrichedLogbookEntry,
    XrayProject,
    XraySample,
)


def _make_entries(*, sampos: str = "Mo B5") -> tuple[MaterialEnrichedLogbookEntry, XrayEnrichedLogbookEntry]:
    entry = LogbookEntry(
        row_index=2,
        convert_to_script=True,
        date=pd.Timestamp("2026-03-03"),
        proposal_id="2025001",
        sample_id=10,
        user="bpauw",
        batch_num=4,
        sample_position_id=sampos,
        matrix_fraction=0.85,
        sample_thickness=0.0001,
        protocol="20241201_standard_configurations.py",
        processing_pipeline="20250415_standard_logq.nxs",
        notes="room temperature",
        bg_date=pd.Timestamp("2026-03-01"),
        bg_number=1,
        dbg_date=None,
        dbg_number=None,
        additional_parameters={"temperature": "20.5", "exposure": "5s"},
    )

    material_sample = MaterialSample(
        sample_id=10,
        sample_name="Reference Sample",
        composition_summary="H2O, Zr",
        components=(
            MaterialComponent(
                phase_key="a",
                component_id="a",
                component_name="Water",
                composition="H2O",
                density=DensityEstimate(
                    value_g_cm3=0.998,
                    kind="true_density",
                    provenance="experimentally_determined",
                ),
                volume_fraction=0.9,
                mass_fraction=0.4,
            ),
            MaterialComponent(
                phase_key="b",
                component_id="b",
                component_name="Zirconium",
                composition="Zr",
                density=DensityEstimate(
                    value_g_cm3=6.5,
                    kind="true_density",
                    provenance="experimentally_determined",
                ),
                volume_fraction=0.1,
                mass_fraction=0.6,
                connection="inside",
                connected_to="a",
            ),
        ),
        sample_density=DensityEstimate(
            value_g_cm3=1.5482,
            kind="apparent_density",
            provenance="estimated_from_mass_fraction",
        ),
        composition=SampleCompositionEstimate(
            element_atom_fractions={"H": 0.4, "O": 0.2, "Zr": 0.1},
            element_mass_fractions={"H": 0.01, "O": 0.19, "Zr": 0.80},
            provenance="estimated_from_mass_fraction",
        ),
        phase_mass_fractions={"a": 0.4, "b": 0.6},
        phase_mass_fraction_provenance="experimentally_determined",
        phase_volume_fractions={"a": 0.9, "b": 0.1},
        phase_volume_fraction_provenance="experimentally_determined",
    )
    material_project = MaterialProject(
        proposal_id="2025001",
        name="MOUSE instrument",
        email="scattering@example.org",
        organisation="BAM",
        title="Compatibility Test",
        description="Writer compatibility contract",
        samples={10: material_sample},
    )
    material_entry = MaterialEnrichedLogbookEntry(
        entry=entry,
        project=material_project,
        sample=material_sample,
        sample_position={"xsam": 1.2, "ysam": 3.4},
    )

    cu_sample = SampleXrayProperties(
        sample_id=10,
        sample_name="Reference Sample",
        energy_kev=8.04,
        phase_properties={
            "a": PhaseXrayProperties(
                component_id="a",
                component_name="Water",
                formula="H2O",
                density_g_cm3=0.998,
                energy_kev=8.04,
                absorption_coefficient_m_inv=1019.8,
                scattering_length_density=ScatteringLengthDensity(
                    real_m_inv2=9.45e14,
                    imag_m_inv2=1.2e12,
                ),
            ),
            "b": PhaseXrayProperties(
                component_id="b",
                component_name="Zirconium",
                formula="Zr",
                density_g_cm3=6.5,
                energy_kev=8.04,
                absorption_coefficient_m_inv=83800.0,
                scattering_length_density=ScatteringLengthDensity(
                    real_m_inv2=48.2e14,
                    imag_m_inv2=5.0e13,
                ),
            ),
        },
        overall_absorption_coefficient_m_inv=9287.82,
        volume_fractions={"a": 0.9, "b": 0.1},
        volume_fraction_source="volume_fraction",
    )
    mo_sample = SampleXrayProperties(
        sample_id=10,
        sample_name="Reference Sample",
        energy_kev=17.4,
        phase_properties={
            "a": PhaseXrayProperties(
                component_id="a",
                component_name="Water",
                formula="H2O",
                density_g_cm3=0.998,
                energy_kev=17.4,
                absorption_coefficient_m_inv=220.0,
                scattering_length_density=ScatteringLengthDensity(
                    real_m_inv2=8.9e14,
                    imag_m_inv2=2.5e11,
                ),
            ),
            "b": PhaseXrayProperties(
                component_id="b",
                component_name="Zirconium",
                formula="Zr",
                density_g_cm3=6.5,
                energy_kev=17.4,
                absorption_coefficient_m_inv=9700.0,
                scattering_length_density=ScatteringLengthDensity(
                    real_m_inv2=44.8e14,
                    imag_m_inv2=7.1e12,
                ),
            ),
        },
        overall_absorption_coefficient_m_inv=1168.0,
        volume_fractions={"a": 0.9, "b": 0.1},
        volume_fraction_source="volume_fraction",
    )
    xray_sample = XraySample(
        sample_id=10,
        sample_name="Reference Sample",
        composition_summary="H2O, Zr",
        components=tuple(),
        standard_xray={"cu_ka": cu_sample, "mo_ka": mo_sample},
    )
    xray_project = XrayProject(
        proposal_id="2025001",
        name="MOUSE instrument",
        email="scattering@example.org",
        organisation="BAM",
        title="Compatibility Test",
        description="Writer compatibility contract",
        samples={10: xray_sample},
    )
    xray_entry = XrayEnrichedLogbookEntry(
        entry=entry,
        project=xray_project,
        sample=xray_sample,
        sample_position={"xsam": 1.2, "ysam": 3.4},
    )

    return material_entry, xray_entry


def test_nexus_metadata_upserter_writes_compatibility_metadata(tmp_path: Path) -> None:
    material_entry, xray_entry = _make_entries()
    file_path = tmp_path / "metadata.nxs"

    NexusMetadataUpserter().upsert_entry(
        file_path,
        material_entry=material_entry,
        xray_entry=xray_entry,
    )

    with h5py.File(file_path, "r") as handle:
        assert handle.attrs["default"] == "entry1"
        assert handle["/entry1"].attrs["NX_class"] == "NXentry"
        assert handle["/entry1/sample"].attrs["NX_class"] == "NXsample"

        assert handle["/entry1/proposal/proposalid"][()] == b"2025001"
        assert handle["/entry1/proposal/proposal_title"][()] == b"Compatibility Test"
        assert handle["/entry1/proposal/proposal_responsible_name"][()] == b"MOUSE instrument"

        assert handle["/entry1/sample/name"][()] == b"Reference Sample"
        assert handle["/entry1/sample/owner"][()] == b"MOUSE instrument"
        assert handle["/entry1/sample/sampleid"][()] == b"10"
        assert handle["/entry1/sample/sampos"][()] == b"Mo B5"
        assert handle["/entry1/sample/composition"][()] == b"H4O2Zr1"
        assert handle["/entry1/sample/transformations"].attrs["NX_class"] == "NXtransformations"
        assert handle["/entry1/sample/transformations/sample_x"][()] == pytest.approx(1.2)
        assert handle["/entry1/sample/transformations/sample_x"].attrs["depends_on"] == "."
        assert handle["/entry1/sample/transformations/sample_x"].attrs["transformation_type"] == "translation"
        assert handle["/entry1/sample/transformations/sample_x"].attrs["units"] == "mm"
        assert handle["/entry1/sample/transformations/sample_x"].attrs["vector"] == pytest.approx([0.0, 0.0, 1.0])
        assert handle["/entry1/sample/matrixfraction"][()] == pytest.approx([0.85])
        assert handle["/entry1/sample/samplethickness"][()] == pytest.approx([0.0001])
        assert handle["/entry1/sample/density"][()] == pytest.approx([1.5482])
        assert handle["/entry1/sample/density"].attrs["units"] == "g/cm^3"
        assert handle["/entry1/sample/density"].attrs["kind"] == "apparent_density"
        assert handle["/entry1/sample/density"].attrs["provenance"] == "estimated_from_mass_fraction"
        assert handle["/entry1/sample/overall_mu"][()] == pytest.approx([1168.0])
        assert handle["/entry1/sample/overall_mu"].attrs["units"] == "1/m"
        assert handle["/entry1/sample/overall_mu"].attrs["source_key"] == "mo_ka"
        assert handle["/entry1/sample/overall_mu"].attrs["energy_kev"] == pytest.approx(17.4)

        assert handle["/entry1/sample/components/a/name"][()] == b"Water"
        assert handle["/entry1/sample/components/a/composition"][()] == b"H2O"
        assert handle["/entry1/sample/components/a/density"][()] == pytest.approx([0.998])
        assert handle["/entry1/sample/components/a/mass_fraction"][()] == pytest.approx([0.4])
        assert handle["/entry1/sample/components/a/volume_fraction"][()] == pytest.approx([0.9])
        assert handle["/entry1/sample/components/a/mu"][()] == pytest.approx([220.0])
        assert handle["/entry1/sample/components/a/sld_real"][()] == pytest.approx([8.9e14])
        assert handle["/entry1/sample/components/a/sld_imag"][()] == pytest.approx([2.5e11])
        assert handle["/entry1/sample/components/b/connection"][()] == b"inside"
        assert handle["/entry1/sample/components/b/connected_to"][()] == b"a"

        assert handle["/entry1/experiment/experiment_identifier"][()] == b"2025001"
        assert handle["/entry1/experiment/logbook_date"][()] == b"20260303"
        assert handle["/entry1/experiment/user"][()] == b"bpauw"
        assert handle["/entry1/experiment/protocol"][()] == b"20241201_standard_configurations.py"
        assert handle["/entry1/experiment/notes"][()] == b"room temperature"
        assert handle["/entry1/experiment/additional_parameters"][()] == b"{'temperature': '20.5', 'exposure': '5s'}"
        assert handle["/entry1/experiment/batchnum"][()] == 4

        assert handle["/entry1/processing_required_metadata/background_identifier"][()] == b"20260301_1"
        assert handle["/entry1/processing_required_metadata/dispersant_background_identifier"][()] == b"None"
        assert handle["/entry1/processing_required_metadata/procpipeline"][()] == b"20250415_standard_logq.nxs"
        assert handle["/entry1/processing_required_metadata/background_file"][()] == b""
        assert handle["/entry1/processing_required_metadata/dispersed_background_file"][()] == b""


def test_nexus_metadata_upserter_preserves_existing_background_file_paths(tmp_path: Path) -> None:
    material_entry, xray_entry = _make_entries()
    file_path = tmp_path / "metadata.nxs"

    with h5py.File(file_path, "w") as handle:
        prm = handle.create_group("entry1").create_group("processing_required_metadata")
        prm.create_dataset("background_file", data="existing_background.nxs", dtype=h5py.string_dtype())
        prm.create_dataset("dispersed_background_file", data="existing_dispersed.nxs", dtype=h5py.string_dtype())

    NexusMetadataUpserter().upsert_entry(
        file_path,
        material_entry=material_entry,
        xray_entry=xray_entry,
    )

    with h5py.File(file_path, "r") as handle:
        assert handle["/entry1/processing_required_metadata/background_file"][()] == b"existing_background.nxs"
        assert handle["/entry1/processing_required_metadata/dispersed_background_file"][()] == b"existing_dispersed.nxs"
        assert handle["/entry1/processing_required_metadata/background_identifier"][()] == b"20260301_1"


def test_nexus_metadata_upserter_preserves_existing_sample_y_and_sample_z_transformations(tmp_path: Path) -> None:
    material_entry, xray_entry = _make_entries()
    file_path = tmp_path / "metadata.nxs"

    with h5py.File(file_path, "w") as handle:
        transformations = handle.create_group("entry1").create_group("sample").create_group("transformations")
        transformations.attrs["NX_class"] = "NXtransformations"
        sample_y = transformations.create_dataset("sample_y", data=2.3)
        sample_y.attrs["units"] = "mm"
        sample_y.attrs["vector"] = [1.0, 0.0, 0.0]
        sample_z = transformations.create_dataset("sample_z", data=4.5)
        sample_z.attrs["units"] = "mm"
        sample_z.attrs["vector"] = [0.0, 1.0, 0.0]

    NexusMetadataUpserter().upsert_entry(
        file_path,
        material_entry=material_entry,
        xray_entry=xray_entry,
    )

    with h5py.File(file_path, "r") as handle:
        assert handle["/entry1/sample/transformations/sample_x"][()] == pytest.approx(1.2)
        assert handle["/entry1/sample/transformations/sample_x"].attrs["units"] == "mm"
        assert handle["/entry1/sample/transformations/sample_y"][()] == pytest.approx(2.3)
        assert handle["/entry1/sample/transformations/sample_y"].attrs["vector"] == pytest.approx([1.0, 0.0, 0.0])
        assert handle["/entry1/sample/transformations/sample_z"][()] == pytest.approx(4.5)
        assert handle["/entry1/sample/transformations/sample_z"].attrs["vector"] == pytest.approx([0.0, 1.0, 0.0])


def test_nexus_metadata_upserter_accepts_explicit_xray_properties_for_nonstandard_energy(tmp_path: Path) -> None:
    material_entry, xray_entry = _make_entries()
    file_path = tmp_path / "metadata.nxs"
    custom_xray = SampleXrayProperties(
        sample_id=10,
        sample_name="Reference Sample",
        energy_kev=12.5,
        phase_properties={
            "a": PhaseXrayProperties(
                component_id="a",
                component_name="Water",
                formula="H2O",
                density_g_cm3=0.998,
                energy_kev=12.5,
                absorption_coefficient_m_inv=500.0,
                scattering_length_density=ScatteringLengthDensity(real_m_inv2=9.0e14, imag_m_inv2=9.0e11),
            ),
            "b": PhaseXrayProperties(
                component_id="b",
                component_name="Zirconium",
                formula="Zr",
                density_g_cm3=6.5,
                energy_kev=12.5,
                absorption_coefficient_m_inv=15000.0,
                scattering_length_density=ScatteringLengthDensity(real_m_inv2=46.0e14, imag_m_inv2=1.1e13),
            ),
        },
        overall_absorption_coefficient_m_inv=1950.0,
        volume_fractions={"a": 0.9, "b": 0.1},
        volume_fraction_source="volume_fraction",
    )

    NexusMetadataUpserter().upsert_entry(
        file_path,
        material_entry=material_entry,
        xray_entry=xray_entry,
        sample_xray=custom_xray,
        source_key="synchrotron_12p5kev",
    )

    with h5py.File(file_path, "r") as handle:
        assert handle["/entry1/sample/overall_mu"][()] == pytest.approx([1950.0])
        assert handle["/entry1/sample/overall_mu"].attrs["source_key"] == "synchrotron_12p5kev"
        assert handle["/entry1/sample/overall_mu"].attrs["energy_kev"] == pytest.approx(12.5)
        assert handle["/entry1/sample/components/b/mu"][()] == pytest.approx([15000.0])


def test_nexus_metadata_upserter_rejects_mismatched_material_and_xray_entries(tmp_path: Path) -> None:
    material_entry, xray_entry = _make_entries()
    mismatched_xray = XrayEnrichedLogbookEntry(
        entry=attrs.evolve(xray_entry.entry, sample_id=99),
        project=xray_entry.project,
        sample=xray_entry.sample,
        sample_position=xray_entry.sample_position,
    )

    with pytest.raises(NexusMetadataError, match="material and X-ray entries do not describe the same measurement"):
        NexusMetadataUpserter().upsert_entry(
            tmp_path / "metadata.nxs",
            material_entry=material_entry,
            xray_entry=mismatched_xray,
        )
