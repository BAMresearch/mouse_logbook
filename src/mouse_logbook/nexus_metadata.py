from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import attrs

from .sample_metadata_materials import MaterialEnrichedLogbookEntry, MaterialSample
from .sample_metadata_xray import SampleXrayProperties, XrayEnrichedLogbookEntry


class NexusMetadataError(RuntimeError):
    """Raised when validated metadata cannot be written into the target NeXus file."""


def _require_h5py():
    try:
        import h5py
    except ModuleNotFoundError as e:
        raise RuntimeError("h5py is not installed") from e
    return h5py


@attrs.define(slots=True)
class NexusMetadataUpserter:
    """Upserts validated logbook/proposal/sample metadata into a NeXus-style HDF5 file.

    Compatibility notes:
    - proposal metadata is written under `/entry1/proposal`
    - sample metadata is written under `/entry1/sample`
    - phase/component metadata is written under `/entry1/sample/components`
    - logbook-driven processing metadata is written under
      `/entry1/processing_required_metadata`
    - the current compatibility target uses the dataset name
      `dispersant_background_identifier` in that processing group
    - `overall_mu` and per-phase `mu`/`sld_*` are written for the selected
      X-ray energy. By default that energy is inferred from `sampos`
      (`Cu ...` -> `cu_ka`, `Mo ...` -> `mo_ka`), but callers can override
      this with `source_key=` or an explicit `sample_xray=...`
    """

    entry_group_name: str = "entry1"
    preserve_external_file_paths: bool = True

    def upsert_entry(
        self,
        file_path: str | Path,
        *,
        material_entry: MaterialEnrichedLogbookEntry,
        xray_entry: XrayEnrichedLogbookEntry,
        sample_xray: SampleXrayProperties | None = None,
        source_key: str | None = None,
    ) -> None:
        self._validate_measurement_match(material_entry=material_entry, xray_entry=xray_entry)

        selected_xray, resolved_source_key = self._select_sample_xray(
            material_entry=material_entry,
            xray_entry=xray_entry,
            sample_xray=sample_xray,
            source_key=source_key,
        )

        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        h5py = _require_h5py()

        with h5py.File(path, "a") as handle:
            entry_group = self._ensure_group(
                handle,
                self.entry_group_name,
                attrs_map={"NX_class": "NXentry", "default": "instrument"},
            )
            handle.attrs["default"] = self.entry_group_name

            proposal_group = self._ensure_group(entry_group, "proposal")
            experiment_group = self._ensure_group(entry_group, "experiment")
            processing_group = self._ensure_group(entry_group, "processing_required_metadata")
            sample_group = self._ensure_group(
                entry_group,
                "sample",
                attrs_map={"NX_class": "NXsample", "default": "name"},
            )

            self._write_proposal_metadata(proposal_group, material_entry)
            self._write_sample_metadata(
                sample_group,
                material_entry=material_entry,
                selected_xray=selected_xray,
                source_key=resolved_source_key,
            )
            self._write_experiment_metadata(experiment_group, material_entry)
            self._write_processing_metadata(processing_group, material_entry)

    def _validate_measurement_match(
        self,
        *,
        material_entry: MaterialEnrichedLogbookEntry,
        xray_entry: XrayEnrichedLogbookEntry,
    ) -> None:
        material_key = (
            material_entry.entry.proposal_id,
            material_entry.entry.sample_id,
            material_entry.entry.row_index,
            material_entry.entry.ymd,
            material_entry.entry.sample_position_id,
        )
        xray_key = (
            xray_entry.entry.proposal_id,
            xray_entry.entry.sample_id,
            xray_entry.entry.row_index,
            xray_entry.entry.ymd,
            xray_entry.entry.sample_position_id,
        )
        if material_key != xray_key:
            raise NexusMetadataError("material and X-ray entries do not describe the same measurement")

    def _select_sample_xray(
        self,
        *,
        material_entry: MaterialEnrichedLogbookEntry,
        xray_entry: XrayEnrichedLogbookEntry,
        sample_xray: SampleXrayProperties | None,
        source_key: str | None,
    ) -> tuple[SampleXrayProperties, str]:
        if sample_xray is not None:
            return sample_xray, (source_key or "custom")

        resolved_source_key = source_key or self._infer_source_key(material_entry.entry.sample_position_id)
        selected_xray = xray_entry.sample.standard_xray.get(resolved_source_key)
        if selected_xray is None:
            raise NexusMetadataError(f"X-ray metadata does not contain a {resolved_source_key!r} entry")
        return selected_xray, resolved_source_key

    def _infer_source_key(self, sampos: str) -> str:
        lowered = sampos.strip().lower()
        tokens = lowered.replace("_", " ").split()
        for token in tokens:
            if token.startswith("cu"):
                return "cu_ka"
            if token.startswith("mo"):
                return "mo_ka"
        raise NexusMetadataError(
            f"could not infer X-ray source from sampos {sampos!r}; pass source_key= or sample_xray= explicitly"
        )

    def _write_proposal_metadata(self, proposal_group: Any, material_entry: MaterialEnrichedLogbookEntry) -> None:
        project = material_entry.project
        self._write_text_dataset(proposal_group, "proposal_description", project.description)
        self._write_text_dataset(proposal_group, "proposal_responsible_email", project.email)
        self._write_text_dataset(proposal_group, "proposal_responsible_name", project.name)
        self._write_text_dataset(proposal_group, "proposal_responsible_organisation", project.organisation)
        self._write_text_dataset(proposal_group, "proposal_title", project.title)
        self._write_text_dataset(proposal_group, "proposalid", project.proposal_id)

    def _write_sample_metadata(
        self,
        sample_group: Any,
        *,
        material_entry: MaterialEnrichedLogbookEntry,
        selected_xray: SampleXrayProperties,
        source_key: str,
    ) -> None:
        entry = material_entry.entry
        project = material_entry.project
        sample = material_entry.sample

        self._write_text_dataset(sample_group, "name", sample.sample_name)
        self._write_text_dataset(sample_group, "owner", project.name)
        self._write_text_dataset(sample_group, "sampleid", str(sample.sample_id))
        self._write_text_dataset(sample_group, "sampos", entry.sample_position_id)
        self._write_text_dataset(
            sample_group,
            "composition",
            self._overall_composition_text(sample),
            attrs_map={"provenance": sample.composition.provenance},
        )
        self._write_float_array_dataset(
            sample_group,
            "density",
            sample.sample_density.value_g_cm3,
            attrs_map={
                "note": "Overall gravimetric density of the sample.",
                "units": "g/cm^3",
                "kind": sample.sample_density.kind or "",
                "provenance": sample.sample_density.provenance,
            },
        )
        self._write_float_array_dataset(
            sample_group,
            "overall_mu",
            selected_xray.overall_absorption_coefficient_m_inv,
            attrs_map={
                "note": "Overall sample absorption coefficient at the selected X-ray energy.",
                "units": "1/m",
                "source_key": source_key,
                "energy_kev": float(selected_xray.energy_kev),
            },
        )
        self._write_float_array_dataset(
            sample_group,
            "matrixfraction",
            entry.matrix_fraction,
            attrs_map={
                "note": "The volume fraction that the matrix takes up in the total sample. For dilute samples, this approaches 1.0",
            },
        )
        self._write_float_array_dataset(
            sample_group,
            "samplethickness",
            entry.sample_thickness,
            attrs_map={
                "note": "The thickness of the sample as specified in the measurement logbook in meters.",
                "units": "m",
            },
        )

        if "components" in sample_group:
            del sample_group["components"]
        components_group = sample_group.create_group("components")
        self._write_component_metadata(
            components_group,
            sample=sample,
            selected_xray=selected_xray,
            source_key=source_key,
        )

    def _write_component_metadata(
        self,
        components_group: Any,
        *,
        sample: MaterialSample,
        selected_xray: SampleXrayProperties,
        source_key: str,
    ) -> None:
        for component in sample.components:
            component_group = components_group.create_group(component.phase_key)
            self._write_text_dataset(component_group, "name", component.component_name or "")
            self._write_text_dataset(component_group, "composition", component.composition)
            self._write_text_dataset(component_group, "connection", component.connection or ".")
            self._write_text_dataset(component_group, "connected_to", component.connected_to or ".")
            self._write_float_array_dataset(
                component_group,
                "density",
                component.density.value_g_cm3,
                attrs_map={
                    "units": "g/cm^3",
                    "kind": component.density.kind or "",
                    "provenance": component.density.provenance,
                },
            )
            self._write_float_array_dataset(
                component_group,
                "mass_fraction",
                sample.phase_mass_fractions.get(component.phase_key, component.mass_fraction),
                attrs_map={"provenance": sample.phase_mass_fraction_provenance},
            )
            self._write_float_array_dataset(
                component_group,
                "volume_fraction",
                sample.phase_volume_fractions.get(component.phase_key, component.volume_fraction),
                attrs_map={"provenance": sample.phase_volume_fraction_provenance},
            )

            phase_xray = selected_xray.phase_properties.get(component.phase_key)
            self._write_float_array_dataset(
                component_group,
                "mu",
                None if phase_xray is None else phase_xray.absorption_coefficient_m_inv,
                attrs_map={
                    "units": "1/m",
                    "source_key": source_key,
                    "energy_kev": float(selected_xray.energy_kev),
                },
            )
            self._write_float_array_dataset(
                component_group,
                "sld_real",
                None if phase_xray is None else phase_xray.scattering_length_density.real_m_inv2,
                attrs_map={
                    "units": "1/m^2",
                    "source_key": source_key,
                    "energy_kev": float(selected_xray.energy_kev),
                },
            )
            self._write_float_array_dataset(
                component_group,
                "sld_imag",
                None if phase_xray is None else phase_xray.scattering_length_density.imag_m_inv2,
                attrs_map={
                    "units": "1/m^2",
                    "source_key": source_key,
                    "energy_kev": float(selected_xray.energy_kev),
                },
            )

    def _write_experiment_metadata(self, experiment_group: Any, material_entry: MaterialEnrichedLogbookEntry) -> None:
        entry = material_entry.entry
        self._write_text_dataset(experiment_group, "additional_parameters", repr(dict(entry.additional_parameters)))
        self._write_int_scalar_dataset(experiment_group, "batchnum", entry.batch_num)
        self._write_text_dataset(experiment_group, "experiment_identifier", entry.proposal_id)
        self._write_text_dataset(experiment_group, "logbook_date", entry.ymd)
        self._write_text_dataset(experiment_group, "notes", entry.notes or "")
        self._write_text_dataset(experiment_group, "protocol", entry.protocol)
        self._write_text_dataset(experiment_group, "user", entry.user)

        self._ensure_text_dataset(experiment_group, "shutter", "")
        self._ensure_float_scalar_dataset(experiment_group, "chamber_pressure", math.nan)
        self._ensure_float_scalar_dataset(experiment_group, "environment_temperature", math.nan)
        self._ensure_float_scalar_dataset(experiment_group, "stage_temperature", math.nan)

    def _write_processing_metadata(self, processing_group: Any, material_entry: MaterialEnrichedLogbookEntry) -> None:
        entry = material_entry.entry
        self._write_text_dataset(
            processing_group,
            "background_identifier",
            self._compose_background_identifier(entry.bg_date, entry.bg_number),
            attrs_map={"note": "Instrument background YMD and measurement group number"},
        )
        self._write_text_dataset(
            processing_group,
            "dispersant_background_identifier",
            self._compose_background_identifier(entry.dbg_date, entry.dbg_number),
            attrs_map={
                "note": "Optional dispersant background YMD and measurement group number. None if not set (i.e. for dilute analytes).",
            },
        )
        self._write_text_dataset(processing_group, "procpipeline", entry.processing_pipeline or "")

        if self.preserve_external_file_paths:
            self._ensure_text_dataset(processing_group, "background_file", "")
            self._ensure_text_dataset(processing_group, "dispersed_background_file", "")
        else:
            self._write_text_dataset(processing_group, "background_file", "")
            self._write_text_dataset(processing_group, "dispersed_background_file", "")

    def _overall_composition_text(self, sample: MaterialSample) -> str:
        atom_fractions = sample.composition.element_atom_fractions
        positive = [value for value in atom_fractions.values() if value > 0]
        if not positive:
            return sample.composition_summary

        scale = min(positive)
        parts = []
        for symbol, fraction in atom_fractions.items():
            if fraction <= 0:
                continue
            parts.append(f"{symbol}{self._format_formula_count(fraction / scale)}")
        return "".join(parts)

    def _format_formula_count(self, value: float) -> str:
        rounded = round(value)
        if math.isclose(value, rounded, abs_tol=1e-12):
            return str(int(rounded))
        return str(float(value))

    def _compose_background_identifier(self, date_value: Any, batch_number: Any) -> str:
        if date_value is None or batch_number is None:
            return "None"
        return f"{date_value.strftime('%Y%m%d')}_{int(batch_number)}"

    def _ensure_group(self, parent: Any, name: str, attrs_map: dict[str, Any] | None = None) -> Any:
        group = parent[name] if name in parent else parent.create_group(name)
        for key, value in (attrs_map or {}).items():
            group.attrs[key] = value
        return group

    def _write_text_dataset(
        self,
        group: Any,
        name: str,
        value: str,
        attrs_map: dict[str, Any] | None = None,
    ) -> None:
        h5py = _require_h5py()
        self._replace_dataset(
            group,
            name,
            value="" if value is None else str(value),
            dtype=h5py.string_dtype(encoding="utf-8"),
            attrs_map=attrs_map,
        )

    def _ensure_text_dataset(self, group: Any, name: str, default: str) -> None:
        if name not in group:
            self._write_text_dataset(group, name, default)

    def _write_int_scalar_dataset(self, group: Any, name: str, value: int, attrs_map: dict[str, Any] | None = None) -> None:
        self._replace_dataset(group, name, value=int(value), attrs_map=attrs_map)

    def _write_float_array_dataset(
        self,
        group: Any,
        name: str,
        value: float | None,
        attrs_map: dict[str, Any] | None = None,
    ) -> None:
        numeric = math.nan if value is None else float(value)
        self._replace_dataset(group, name, value=[numeric], attrs_map=attrs_map)

    def _ensure_float_scalar_dataset(self, group: Any, name: str, default: float) -> None:
        if name not in group:
            self._replace_dataset(group, name, value=float(default))

    def _replace_dataset(
        self,
        group: Any,
        name: str,
        *,
        value: Any,
        dtype: Any | None = None,
        attrs_map: dict[str, Any] | None = None,
    ) -> None:
        if name in group:
            del group[name]

        if dtype is None:
            dataset = group.create_dataset(name, data=value)
        else:
            dataset = group.create_dataset(name, data=value, dtype=dtype)

        for key, attr_value in (attrs_map or {}).items():
            dataset.attrs[key] = attr_value
