from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Protocol

import attrs

from .models import LogbookEntry
from .sample_metadata_chemistry import (
    ChemistryValidatedComponent,
    ChemistryValidatedEnrichedLogbookEntry,
    ChemistryValidatedProject,
    ChemistryValidatedSample,
)
from .validation import ValidationIssue, ValidationReport

STANDARD_XRAY_ENERGIES_KEV: dict[str, float] = {
    "cu_ka": 8.04,
    "mo_ka": 17.4,
}


def _error(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="error", location=location, message=message)


def _warning(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="warning", location=location, message=message)


@attrs.frozen(kw_only=True, slots=True)
class ScatteringLengthDensity:
    real_m_inv2: float
    imag_m_inv2: float | None = None


@attrs.frozen(kw_only=True, slots=True)
class PhaseXrayProperties:
    component_id: str
    component_name: str | None = None
    formula: str
    density_g_cm3: float
    energy_kev: float
    absorption_coefficient_m_inv: float
    scattering_length_density: ScatteringLengthDensity


@attrs.frozen(kw_only=True, slots=True)
class SampleXrayProperties:
    sample_id: int
    sample_name: str
    energy_kev: float
    phase_properties: dict[str, PhaseXrayProperties] = attrs.field(factory=dict, converter=dict)
    overall_absorption_coefficient_m_inv: float | None = None
    volume_fractions: dict[str, float] = attrs.field(factory=dict, converter=dict)
    volume_fraction_source: str = "unavailable"


@attrs.frozen(kw_only=True, slots=True)
class XraySample:
    sample_id: int
    sample_name: str
    composition_summary: str
    components: tuple[ChemistryValidatedComponent, ...] = attrs.field(factory=tuple)
    standard_xray: dict[str, SampleXrayProperties] = attrs.field(factory=dict, converter=dict)


@attrs.frozen(kw_only=True, slots=True)
class XrayProject:
    proposal_id: str
    name: str
    email: str
    organisation: str
    title: str
    description: str
    samples: dict[int, XraySample] = attrs.field(factory=dict, converter=dict)


@attrs.frozen(kw_only=True, slots=True)
class XrayEnrichedLogbookEntry:
    entry: LogbookEntry
    project: XrayProject
    sample: XraySample
    sample_position: Mapping[str, float] = attrs.field(factory=dict)


class XrayBackend(Protocol):
    def calculate_component(self, *, formula_text: str, density: float, energy_kev: float) -> tuple[float, float, float]: ...


@attrs.define(slots=True)
class PeriodictableXrayBackend:
    """X-ray property backend using xraydb and periodictable."""

    def calculate_component(self, *, formula_text: str, density: float, energy_kev: float) -> tuple[float, float, float]:
        try:
            import xraydb
        except ModuleNotFoundError as e:
            raise RuntimeError("xraydb is not installed") from e

        try:
            from periodictable.xsf import xray_sld
        except ModuleNotFoundError as e:
            raise RuntimeError("periodictable is not installed") from e

        mu_cm_inv = xraydb.material_mu(formula_text, density=density, energy=energy_kev * 1000.0)
        sld_real, sld_imag = xray_sld(formula_text, density=density, energy=energy_kev)

        return (
            float(mu_cm_inv) * 100.0,
            float(sld_real) * 1e14,
            float(sld_imag) * 1e14,
        )


@attrs.define(slots=True)
class SampleMetadataXrayCalculator:
    """Computes phase and sample X-ray properties from chemistry-validated metadata."""

    backend: XrayBackend = attrs.field(factory=PeriodictableXrayBackend)
    standard_energies_kev: dict[str, float] = attrs.field(factory=lambda: dict(STANDARD_XRAY_ENERGIES_KEV), converter=dict)

    def calculate_sample_at_energy(
        self,
        sample: ChemistryValidatedSample,
        *,
        energy_kev: float,
    ) -> ValidationReport[SampleXrayProperties]:
        issues: list[ValidationIssue] = []
        location = f"Sample_Metadata_Xray sampleId={sample.sample_id}"
        phase_properties: dict[str, PhaseXrayProperties] = {}
        phase_components: list[tuple[str, ChemistryValidatedComponent]] = []
        used_phase_keys: set[str] = set()

        for index, component in enumerate(sample.components, start=1):
            phase_key = self._phase_key(
                component=component,
                component_index=index,
                sample_id=sample.sample_id,
                used_phase_keys=used_phase_keys,
                issues=issues,
            )
            component_report = self._calculate_component_at_energy(component, energy_kev=energy_kev, location=location)
            issues.extend(component_report.issues)
            if component_report.value is None:
                continue
            phase_properties[phase_key] = component_report.value
            phase_components.append((phase_key, component))

        overall_mu: float | None = None
        volume_fractions: dict[str, float] = {}
        volume_fraction_source = "unavailable"
        if len(phase_components) == len(sample.components):
            (
                volume_fractions,
                volume_fraction_source,
                volume_fraction_issues,
            ) = self._resolve_volume_fractions(phase_components=phase_components, location=location)
            issues.extend(volume_fraction_issues)
            if volume_fractions:
                overall_mu = sum(
                    volume_fractions[phase_key] * phase_properties[phase_key].absorption_coefficient_m_inv
                    for phase_key, _ in phase_components
                )
        elif sample.components:
            issues.append(
                _warning(
                    location,
                    "overall absorption unavailable because one or more components could not be evaluated "
                    "for X-ray properties",
                )
            )

        return ValidationReport(
            value=SampleXrayProperties(
                sample_id=sample.sample_id,
                sample_name=sample.sample_name,
                energy_kev=float(energy_kev),
                phase_properties=phase_properties,
                overall_absorption_coefficient_m_inv=overall_mu,
                volume_fractions=volume_fractions,
                volume_fraction_source=volume_fraction_source,
            ),
            issues=tuple(issues),
        )

    def precompute_sample(self, sample: ChemistryValidatedSample) -> ValidationReport[XraySample]:
        issues: list[ValidationIssue] = []
        standard_xray: dict[str, SampleXrayProperties] = {}

        for source_name, energy_kev in self.standard_energies_kev.items():
            sample_report = self.calculate_sample_at_energy(sample, energy_kev=energy_kev)
            issues.extend(sample_report.issues)
            standard_xray[source_name] = sample_report.value

        return ValidationReport(
            value=XraySample(
                sample_id=sample.sample_id,
                sample_name=sample.sample_name,
                composition_summary=sample.composition_summary,
                components=sample.components,
                standard_xray=standard_xray,
            ),
            issues=tuple(issues),
        )

    def precompute_project(self, project: ChemistryValidatedProject) -> ValidationReport[XrayProject]:
        issues: list[ValidationIssue] = []
        samples: dict[int, XraySample] = {}

        for sample_id, sample in project.samples.items():
            sample_report = self.precompute_sample(sample)
            issues.extend(sample_report.issues)
            samples[sample_id] = sample_report.value

        return ValidationReport(
            value=XrayProject(
                proposal_id=project.proposal_id,
                name=project.name,
                email=project.email,
                organisation=project.organisation,
                title=project.title,
                description=project.description,
                samples=samples,
            ),
            issues=tuple(issues),
        )

    def precompute_enriched_entry(
        self,
        enriched: ChemistryValidatedEnrichedLogbookEntry,
    ) -> ValidationReport[XrayEnrichedLogbookEntry]:
        project_report = self.precompute_project(enriched.project)
        issues = list(project_report.issues)

        project_sample = project_report.value.samples.get(enriched.entry.sample_id)
        if project_sample is None:
            sample_report = self.precompute_sample(enriched.sample)
            issues.extend(sample_report.issues)
            sample = sample_report.value
            issues.append(
                _error(
                    "Sample_Metadata_Xray",
                    f"sampleId={enriched.entry.sample_id} missing from X-ray project for proposal "
                    f"{enriched.entry.proposal_id}",
                )
            )
        else:
            sample = project_sample

        return ValidationReport(
            value=XrayEnrichedLogbookEntry(
                entry=enriched.entry,
                project=project_report.value,
                sample=sample,
                sample_position=enriched.sample_position,
            ),
            issues=tuple(issues),
        )

    def precompute_enriched_entries(
        self,
        entries: Iterable[ChemistryValidatedEnrichedLogbookEntry],
    ) -> ValidationReport[list[XrayEnrichedLogbookEntry]]:
        values: list[XrayEnrichedLogbookEntry] = []
        issues: list[ValidationIssue] = []

        for enriched in entries:
            report = self.precompute_enriched_entry(enriched)
            values.append(report.value)
            issues.extend(report.issues)

        return ValidationReport(value=values, issues=tuple(issues))

    def _calculate_component_at_energy(
        self,
        component: ChemistryValidatedComponent,
        *,
        energy_kev: float,
        location: str,
    ) -> ValidationReport[PhaseXrayProperties | None]:
        issues: list[ValidationIssue] = []
        component_label = component.component_id or "<missing component_id>"

        if component.formula is None:
            issues.append(
                _error(
                    location,
                    f"component {component_label!r} is missing parsed chemistry formula required for X-ray properties",
                )
            )
            return ValidationReport(value=None, issues=tuple(issues))

        if component.density is None:
            issues.append(
                _error(location, f"component {component_label!r} is missing density required for X-ray properties")
            )
            return ValidationReport(value=None, issues=tuple(issues))

        if component.density <= 0:
            issues.append(_error(location, f"component {component_label!r} has non-positive density"))
            return ValidationReport(value=None, issues=tuple(issues))

        try:
            mu_m_inv, sld_real_m_inv2, sld_imag_m_inv2 = self.backend.calculate_component(
                formula_text=component.formula.normalized_formula,
                density=component.density,
                energy_kev=energy_kev,
            )
        except Exception as e:
            issues.append(
                _error(
                    location,
                    f"component {component_label!r} failed X-ray calculation at {energy_kev:g} keV: {e}",
                )
            )
            return ValidationReport(value=None, issues=tuple(issues))

        if not all(math.isfinite(value) for value in (mu_m_inv, sld_real_m_inv2, sld_imag_m_inv2)):
            issues.append(
                _error(
                    location,
                    f"component {component_label!r} produced non-finite X-ray properties at {energy_kev:g} keV",
                )
            )
            return ValidationReport(value=None, issues=tuple(issues))

        return ValidationReport(
            value=PhaseXrayProperties(
                component_id=component.component_id,
                component_name=component.component_name,
                formula=component.formula.normalized_formula,
                density_g_cm3=component.density,
                energy_kev=float(energy_kev),
                absorption_coefficient_m_inv=float(mu_m_inv),
                scattering_length_density=ScatteringLengthDensity(
                    real_m_inv2=float(sld_real_m_inv2),
                    imag_m_inv2=float(sld_imag_m_inv2),
                ),
            ),
            issues=tuple(issues),
        )

    def _phase_key(
        self,
        *,
        component: ChemistryValidatedComponent,
        component_index: int,
        sample_id: int,
        used_phase_keys: set[str],
        issues: list[ValidationIssue],
    ) -> str:
        base_key = component.component_id.strip() or f"component_{component_index}"
        if not component.component_id.strip():
            issues.append(
                _warning(
                    f"Sample_Metadata_Xray sampleId={sample_id}",
                    f"component row {component_index} is missing component_id; using {base_key!r} for X-ray results",
                )
            )

        phase_key = base_key
        suffix = 2
        while phase_key in used_phase_keys:
            phase_key = f"{base_key}#{suffix}"
            suffix += 1

        if phase_key != base_key:
            issues.append(
                _warning(
                    f"Sample_Metadata_Xray sampleId={sample_id}",
                    f"duplicate component_id {base_key!r} detected; using {phase_key!r} for X-ray results",
                )
            )

        used_phase_keys.add(phase_key)
        return phase_key

    def _resolve_volume_fractions(
        self,
        *,
        phase_components: list[tuple[str, ChemistryValidatedComponent]],
        location: str,
    ) -> tuple[dict[str, float], str, tuple[ValidationIssue, ...]]:
        issues: list[ValidationIssue] = []
        components = [component for _, component in phase_components]

        if components and all(component.volume_fraction is not None for component in components):
            raw_volume_fractions = {
                phase_key: float(component.volume_fraction)
                for phase_key, component in phase_components
                if component.volume_fraction is not None
            }
            normalized, normalize_issues = self._normalize_fractions(
                raw_volume_fractions,
                location=location,
                fraction_label="volume_fraction",
            )
            issues.extend(normalize_issues)
            return normalized, ("volume_fraction" if normalized else "unavailable"), tuple(issues)

        if components and all(component.mass_fraction is not None for component in components):
            raw_mass_fractions = {
                phase_key: float(component.mass_fraction)
                for phase_key, component in phase_components
                if component.mass_fraction is not None
            }
            normalized_mass_fractions, normalize_issues = self._normalize_fractions(
                raw_mass_fractions,
                location=location,
                fraction_label="mass_fraction",
            )
            issues.extend(normalize_issues)
            if not normalized_mass_fractions:
                return {}, "unavailable", tuple(issues)

            numerators: dict[str, float] = {}
            for phase_key, component in phase_components:
                if component.density is None or component.density <= 0:
                    issues.append(
                        _warning(
                            location,
                            "overall absorption unavailable because one or more mass-fraction components "
                            "is missing positive density",
                        )
                    )
                    return {}, "unavailable", tuple(issues)
                numerators[phase_key] = normalized_mass_fractions[phase_key] / component.density

            total = sum(numerators.values())
            if total <= 0:
                issues.append(
                    _warning(location, "overall absorption unavailable because derived volume fractions are invalid")
                )
                return {}, "unavailable", tuple(issues)

            return (
                {phase_key: numerator / total for phase_key, numerator in numerators.items()},
                "derived_from_mass_fraction",
                tuple(issues),
            )

        if any(component.volume_fraction is not None for component in components):
            issues.append(
                _warning(
                    location,
                    "overall absorption unavailable because volume_fraction is only provided for some components",
                )
            )
        elif any(component.mass_fraction is not None for component in components):
            issues.append(
                _warning(
                    location,
                    "overall absorption unavailable because mass_fraction is only provided for some components",
                )
            )
        else:
            issues.append(
                _warning(
                    location,
                    "overall absorption unavailable because neither volume_fraction nor mass_fraction is available "
                    "for every component",
                )
            )

        return {}, "unavailable", tuple(issues)

    def _normalize_fractions(
        self,
        fractions: Mapping[str, float],
        *,
        location: str,
        fraction_label: str,
    ) -> tuple[dict[str, float], tuple[ValidationIssue, ...]]:
        issues: list[ValidationIssue] = []
        total = sum(fractions.values())

        if total <= 0:
            issues.append(
                _warning(location, f"{fraction_label} sum is {total:.6f}; overall absorption is unavailable")
            )
            return {}, tuple(issues)

        if any(value < 0 for value in fractions.values()):
            issues.append(_warning(location, f"{fraction_label} contains negative values; overall absorption is unavailable"))
            return {}, tuple(issues)

        normalized = dict(fractions)
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            issues.append(
                _warning(location, f"{fraction_label} sums to {total:.6f}; normalizing for overall absorption")
            )
            normalized = {key: value / total for key, value in fractions.items()}

        return normalized, tuple(issues)
