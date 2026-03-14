from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Literal, Protocol

import attrs

from .models import LogbookEntry
from .sample_metadata_chemistry import (
    ChemistryValidatedComponent,
    ChemistryValidatedEnrichedLogbookEntry,
    ChemistryValidatedProject,
    ChemistryValidatedSample,
    ParsedChemicalFormula,
)
from .validation import ValidationIssue, ValidationReport

MaterialProvenance = Literal[
    "experimentally_determined",
    "estimated_from_volume_fraction",
    "estimated_from_mass_fraction",
    "unavailable",
]
DensityKind = Literal["apparent_density", "true_density", "skeletal_density"]


def _error(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="error", location=location, message=message)


def _warning(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="warning", location=location, message=message)


@attrs.frozen(kw_only=True, slots=True)
class FormulaMaterialProperties:
    molar_mass_g_mol: float
    element_mass_fractions: Mapping[str, float] = attrs.field(
        converter=lambda value: {str(k): float(v) for k, v in dict(value).items()},
        factory=dict,
    )
    element_atom_fractions: Mapping[str, float] = attrs.field(
        converter=lambda value: {str(k): float(v) for k, v in dict(value).items()},
        factory=dict,
    )


@attrs.frozen(kw_only=True, slots=True)
class DensityEstimate:
    value_g_cm3: float | None = None
    kind: DensityKind | None = None
    provenance: MaterialProvenance = "unavailable"


@attrs.frozen(kw_only=True, slots=True)
class SampleCompositionEstimate:
    element_mass_fractions: dict[str, float] = attrs.field(factory=dict, converter=dict)
    element_atom_fractions: dict[str, float] = attrs.field(factory=dict, converter=dict)
    provenance: MaterialProvenance = "unavailable"


@attrs.frozen(kw_only=True, slots=True)
class MaterialComponent:
    phase_key: str = ""
    component_id: str
    composition: str
    density: DensityEstimate = attrs.field(factory=DensityEstimate)
    volume_fraction: float | None = None
    mass_fraction: float | None = None
    connection: str | None = None
    connected_to: str | None = None
    component_name: str | None = None
    formula: ParsedChemicalFormula | None = None
    formula_properties: FormulaMaterialProperties | None = None


@attrs.frozen(kw_only=True, slots=True)
class MaterialSample:
    sample_id: int
    sample_name: str
    composition_summary: str
    components: tuple[MaterialComponent, ...] = attrs.field(factory=tuple)
    sample_density: DensityEstimate = attrs.field(factory=DensityEstimate)
    composition: SampleCompositionEstimate = attrs.field(factory=SampleCompositionEstimate)
    phase_mass_fractions: dict[str, float] = attrs.field(factory=dict, converter=dict)
    phase_mass_fraction_provenance: MaterialProvenance = "unavailable"
    phase_volume_fractions: dict[str, float] = attrs.field(factory=dict, converter=dict)
    phase_volume_fraction_provenance: MaterialProvenance = "unavailable"


@attrs.frozen(kw_only=True, slots=True)
class MaterialProject:
    proposal_id: str
    name: str
    email: str
    organisation: str
    title: str
    description: str
    samples: dict[int, MaterialSample] = attrs.field(factory=dict, converter=dict)


@attrs.frozen(kw_only=True, slots=True)
class MaterialEnrichedLogbookEntry:
    entry: LogbookEntry
    project: MaterialProject
    sample: MaterialSample
    sample_position: Mapping[str, float] = attrs.field(factory=dict)


class MaterialInterpreter(Protocol):
    def characterize_formula(self, formula: ParsedChemicalFormula) -> FormulaMaterialProperties: ...


@attrs.define(slots=True)
class PeriodictableMaterialInterpreter:
    """Computes formula-level mass and elemental fractions using periodictable."""

    def characterize_formula(self, formula: ParsedChemicalFormula) -> FormulaMaterialProperties:
        try:
            import periodictable as pt
        except ModuleNotFoundError as e:
            raise RuntimeError("periodictable is not installed") from e

        atom_total = 0.0
        molar_mass = 0.0
        mass_contributions: dict[str, float] = {}

        for symbol, count in formula.atom_counts.items():
            if count <= 0:
                raise ValueError(f"formula {formula.normalized_formula!r} contains non-positive atom count for {symbol!r}")

            element = getattr(pt, symbol, None)
            if element is None:
                raise ValueError(f"unknown element symbol {symbol!r} in formula {formula.normalized_formula!r}")

            atomic_mass = float(getattr(element, "mass", 0.0))
            if atomic_mass <= 0:
                raise ValueError(f"element {symbol!r} has invalid atomic mass")

            atom_total += count
            contribution = atomic_mass * count
            molar_mass += contribution
            mass_contributions[symbol] = mass_contributions.get(symbol, 0.0) + contribution

        if atom_total <= 0 or molar_mass <= 0:
            raise ValueError(f"formula {formula.normalized_formula!r} has invalid total mass or atom count")

        return FormulaMaterialProperties(
            molar_mass_g_mol=molar_mass,
            element_mass_fractions={symbol: value / molar_mass for symbol, value in mass_contributions.items()},
            element_atom_fractions={symbol: count / atom_total for symbol, count in formula.atom_counts.items()},
        )


@attrs.define(slots=True)
class SampleMetadataMaterialsCalculator:
    """Derives sample-level composition and density from chemistry-validated metadata.

    Current density semantics:
    - component densities provided in the proposal sheet are treated as
      `true_density` unless a richer schema is added later
    - sample densities derived from phase fractions are exposed as
      `apparent_density`
    - `skeletal_density` remains representable in the model, but is not
      inferable from the current proposal-sheet inputs
    """

    interpreter: MaterialInterpreter = attrs.field(factory=PeriodictableMaterialInterpreter)

    def characterize_component(self, component: ChemistryValidatedComponent) -> ValidationReport[MaterialComponent]:
        issues: list[ValidationIssue] = []
        formula_properties: FormulaMaterialProperties | None = None
        density = DensityEstimate()

        if component.density is not None:
            if component.density <= 0:
                issues.append(
                    _error("Sample_Metadata_Materials", f"component {component.component_id!r} has non-positive density")
                )
            else:
                density = DensityEstimate(
                    value_g_cm3=component.density,
                    kind="true_density",
                    provenance="experimentally_determined",
                )

        if component.formula is None:
            issues.append(
                _error(
                    "Sample_Metadata_Materials",
                    f"component {component.component_id!r} is missing parsed chemistry formula required for material estimates",
                )
            )
        else:
            try:
                formula_properties = self.interpreter.characterize_formula(component.formula)
            except Exception as e:
                issues.append(
                    _error(
                        "Sample_Metadata_Materials",
                        f"component {component.component_id!r} failed material characterization for "
                        f"{component.composition!r}: {e}",
                    )
                )

        return ValidationReport(
            value=MaterialComponent(
                component_id=component.component_id,
                composition=component.composition,
                density=density,
                volume_fraction=component.volume_fraction,
                mass_fraction=component.mass_fraction,
                connection=component.connection,
                connected_to=component.connected_to,
                component_name=component.component_name,
                formula=component.formula,
                formula_properties=formula_properties,
            ),
            issues=tuple(issues),
        )

    def estimate_sample(self, sample: ChemistryValidatedSample) -> ValidationReport[MaterialSample]:
        issues: list[ValidationIssue] = []
        components: list[MaterialComponent] = []
        used_phase_keys: set[str] = set()

        for index, component in enumerate(sample.components, start=1):
            component_report = self.characterize_component(component)
            issues.extend(component_report.issues)
            phase_key = self._phase_key(
                component=component_report.value,
                component_index=index,
                sample_id=sample.sample_id,
                used_phase_keys=used_phase_keys,
                issues=issues,
            )
            components.append(attrs.evolve(component_report.value, phase_key=phase_key))

        phase_mass_fractions, phase_mass_provenance, mass_fraction_issues = self._resolve_phase_mass_fractions(
            components=components,
            sample_id=sample.sample_id,
        )
        issues.extend(mass_fraction_issues)

        (
            phase_volume_fractions,
            phase_volume_provenance,
            volume_fraction_issues,
        ) = self._resolve_phase_volume_fractions(components=components, sample_id=sample.sample_id)
        issues.extend(volume_fraction_issues)

        sample_density, density_issues = self._estimate_sample_density(
            components=components,
            phase_mass_fractions=phase_mass_fractions,
            phase_mass_fraction_provenance=phase_mass_provenance,
            phase_volume_fractions=phase_volume_fractions,
            phase_volume_fraction_provenance=phase_volume_provenance,
            sample_id=sample.sample_id,
        )
        issues.extend(density_issues)

        composition, composition_issues = self._estimate_sample_composition(
            components=components,
            phase_mass_fractions=phase_mass_fractions,
            phase_mass_fraction_provenance=phase_mass_provenance,
            sample_id=sample.sample_id,
        )
        issues.extend(composition_issues)

        return ValidationReport(
            value=MaterialSample(
                sample_id=sample.sample_id,
                sample_name=sample.sample_name,
                composition_summary=sample.composition_summary,
                components=tuple(components),
                sample_density=sample_density,
                composition=composition,
                phase_mass_fractions=phase_mass_fractions,
                phase_mass_fraction_provenance=phase_mass_provenance,
                phase_volume_fractions=phase_volume_fractions,
                phase_volume_fraction_provenance=phase_volume_provenance,
            ),
            issues=tuple(issues),
        )

    def estimate_project(self, project: ChemistryValidatedProject) -> ValidationReport[MaterialProject]:
        issues: list[ValidationIssue] = []
        samples: dict[int, MaterialSample] = {}

        for sample_id, sample in project.samples.items():
            sample_report = self.estimate_sample(sample)
            issues.extend(sample_report.issues)
            samples[sample_id] = sample_report.value

        return ValidationReport(
            value=MaterialProject(
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

    def estimate_enriched_entry(
        self,
        enriched: ChemistryValidatedEnrichedLogbookEntry,
    ) -> ValidationReport[MaterialEnrichedLogbookEntry]:
        project_report = self.estimate_project(enriched.project)
        issues = list(project_report.issues)

        project_sample = project_report.value.samples.get(enriched.entry.sample_id)
        if project_sample is None:
            sample_report = self.estimate_sample(enriched.sample)
            issues.extend(sample_report.issues)
            sample = sample_report.value
            issues.append(
                _error(
                    "Sample_Metadata_Materials",
                    f"sampleId={enriched.entry.sample_id} missing from material-estimated project for proposal "
                    f"{enriched.entry.proposal_id}",
                )
            )
        else:
            sample = project_sample

        return ValidationReport(
            value=MaterialEnrichedLogbookEntry(
                entry=enriched.entry,
                project=project_report.value,
                sample=sample,
                sample_position=enriched.sample_position,
            ),
            issues=tuple(issues),
        )

    def estimate_enriched_entries(
        self,
        entries: Iterable[ChemistryValidatedEnrichedLogbookEntry],
    ) -> ValidationReport[list[MaterialEnrichedLogbookEntry]]:
        values: list[MaterialEnrichedLogbookEntry] = []
        issues: list[ValidationIssue] = []

        for enriched in entries:
            report = self.estimate_enriched_entry(enriched)
            values.append(report.value)
            issues.extend(report.issues)

        return ValidationReport(value=values, issues=tuple(issues))

    def _phase_key(
        self,
        *,
        component: MaterialComponent,
        component_index: int,
        sample_id: int,
        used_phase_keys: set[str],
        issues: list[ValidationIssue],
    ) -> str:
        base_key = component.component_id.strip() or f"component_{component_index}"
        if not component.component_id.strip():
            issues.append(
                _warning(
                    f"Sample_Metadata_Materials sampleId={sample_id}",
                    f"component row {component_index} is missing component_id; using {base_key!r} for material results",
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
                    f"Sample_Metadata_Materials sampleId={sample_id}",
                    f"duplicate component_id {base_key!r} detected; using {phase_key!r} for material results",
                )
            )

        used_phase_keys.add(phase_key)
        return phase_key

    def _resolve_phase_mass_fractions(
        self,
        *,
        components: list[MaterialComponent],
        sample_id: int,
    ) -> tuple[dict[str, float], MaterialProvenance, tuple[ValidationIssue, ...]]:
        location = f"Sample_Metadata_Materials sampleId={sample_id}"
        issues: list[ValidationIssue] = []

        if components and all(component.mass_fraction is not None for component in components):
            normalized, normalize_issues = self._normalize_fractions(
                {component.phase_key: float(component.mass_fraction) for component in components if component.mass_fraction is not None},
                location=location,
                fraction_label="mass_fraction",
            )
            issues.extend(normalize_issues)
            return normalized, ("experimentally_determined" if normalized else "unavailable"), tuple(issues)

        if components and all(component.volume_fraction is not None for component in components):
            numerators: dict[str, float] = {}
            for component in components:
                density = component.density.value_g_cm3
                if density is None or density <= 0:
                    issues.append(
                        _warning(
                            location,
                            "phase mass fractions unavailable because one or more volume-fraction components is "
                            "missing positive density",
                        )
                    )
                    return {}, "unavailable", tuple(issues)
                numerators[component.phase_key] = float(component.volume_fraction) * density

            total = sum(numerators.values())
            if total <= 0:
                issues.append(_warning(location, "phase mass fractions unavailable because derived masses are invalid"))
                return {}, "unavailable", tuple(issues)

            return (
                {phase_key: numerator / total for phase_key, numerator in numerators.items()},
                "estimated_from_volume_fraction",
                tuple(issues),
            )

        issues.append(
            _warning(
                location,
                "phase mass fractions unavailable because neither complete mass_fraction nor complete "
                "volume_fraction+density data is available",
            )
        )
        return {}, "unavailable", tuple(issues)

    def _resolve_phase_volume_fractions(
        self,
        *,
        components: list[MaterialComponent],
        sample_id: int,
    ) -> tuple[dict[str, float], MaterialProvenance, tuple[ValidationIssue, ...]]:
        location = f"Sample_Metadata_Materials sampleId={sample_id}"
        issues: list[ValidationIssue] = []

        if components and all(component.volume_fraction is not None for component in components):
            normalized, normalize_issues = self._normalize_fractions(
                {
                    component.phase_key: float(component.volume_fraction)
                    for component in components
                    if component.volume_fraction is not None
                },
                location=location,
                fraction_label="volume_fraction",
            )
            issues.extend(normalize_issues)
            return normalized, ("experimentally_determined" if normalized else "unavailable"), tuple(issues)

        if components and all(component.mass_fraction is not None for component in components):
            numerators: dict[str, float] = {}
            for component in components:
                density = component.density.value_g_cm3
                if density is None or density <= 0:
                    issues.append(
                        _warning(
                            location,
                            "phase volume fractions unavailable because one or more mass-fraction components is "
                            "missing positive density",
                        )
                    )
                    return {}, "unavailable", tuple(issues)
                numerators[component.phase_key] = float(component.mass_fraction) / density

            total = sum(numerators.values())
            if total <= 0:
                issues.append(
                    _warning(location, "phase volume fractions unavailable because derived volumes are invalid")
                )
                return {}, "unavailable", tuple(issues)

            return (
                {phase_key: numerator / total for phase_key, numerator in numerators.items()},
                "estimated_from_mass_fraction",
                tuple(issues),
            )

        issues.append(
            _warning(
                location,
                "phase volume fractions unavailable because neither complete volume_fraction nor complete "
                "mass_fraction+density data is available",
            )
        )
        return {}, "unavailable", tuple(issues)

    def _estimate_sample_density(
        self,
        *,
        components: list[MaterialComponent],
        phase_mass_fractions: Mapping[str, float],
        phase_mass_fraction_provenance: MaterialProvenance,
        phase_volume_fractions: Mapping[str, float],
        phase_volume_fraction_provenance: MaterialProvenance,
        sample_id: int,
    ) -> tuple[DensityEstimate, tuple[ValidationIssue, ...]]:
        location = f"Sample_Metadata_Materials sampleId={sample_id}"

        if phase_volume_fractions and all(component.density.value_g_cm3 is not None for component in components):
            value = sum(
                phase_volume_fractions[component.phase_key] * float(component.density.value_g_cm3)
                for component in components
            )
            provenance: MaterialProvenance
            if phase_volume_fraction_provenance == "experimentally_determined":
                provenance = "estimated_from_volume_fraction"
            elif phase_volume_fraction_provenance == "estimated_from_mass_fraction":
                provenance = "estimated_from_mass_fraction"
            else:
                provenance = "unavailable"

            return DensityEstimate(value_g_cm3=value, kind="apparent_density", provenance=provenance), tuple()

        issues: list[ValidationIssue] = []
        if phase_mass_fractions or phase_volume_fractions:
            issues.append(_warning(location, "sample density unavailable because one or more component densities are missing"))
        else:
            issues.append(_warning(location, "sample density unavailable because phase fractions are unavailable"))
        return DensityEstimate(), tuple(issues)

    def _estimate_sample_composition(
        self,
        *,
        components: list[MaterialComponent],
        phase_mass_fractions: Mapping[str, float],
        phase_mass_fraction_provenance: MaterialProvenance,
        sample_id: int,
    ) -> tuple[SampleCompositionEstimate, tuple[ValidationIssue, ...]]:
        location = f"Sample_Metadata_Materials sampleId={sample_id}"
        issues: list[ValidationIssue] = []

        if not phase_mass_fractions:
            issues.append(_warning(location, "sample composition unavailable because phase mass fractions unavailable"))
            return SampleCompositionEstimate(), tuple(issues)

        if any(component.formula_properties is None for component in components):
            issues.append(
                _warning(
                    location,
                    "sample composition unavailable because one or more components lacks materialized formula properties",
                )
            )
            return SampleCompositionEstimate(), tuple(issues)

        element_mass_fractions: dict[str, float] = {}
        atom_contributions: dict[str, float] = {}

        for component in components:
            mass_fraction = phase_mass_fractions[component.phase_key]
            assert component.formula_properties is not None
            assert component.formula is not None

            for symbol, element_mass_fraction in component.formula_properties.element_mass_fractions.items():
                element_mass_fractions[symbol] = (
                    element_mass_fractions.get(symbol, 0.0) + mass_fraction * element_mass_fraction
                )

            for symbol, atom_count in component.formula.atom_counts.items():
                atom_contributions[symbol] = (
                    atom_contributions.get(symbol, 0.0)
                    + mass_fraction * (atom_count / component.formula_properties.molar_mass_g_mol)
                )

        atom_total = sum(atom_contributions.values())
        if atom_total <= 0:
            issues.append(_warning(location, "sample composition unavailable because derived atom fractions are invalid"))
            return SampleCompositionEstimate(), tuple(issues)

        provenance: MaterialProvenance
        if phase_mass_fraction_provenance == "experimentally_determined":
            provenance = "estimated_from_mass_fraction"
        elif phase_mass_fraction_provenance == "estimated_from_volume_fraction":
            provenance = "estimated_from_volume_fraction"
        else:
            provenance = "unavailable"

        return (
            SampleCompositionEstimate(
                element_mass_fractions=element_mass_fractions,
                element_atom_fractions={
                    symbol: contribution / atom_total for symbol, contribution in atom_contributions.items()
                },
                provenance=provenance,
            ),
            tuple(issues),
        )

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
            issues.append(_warning(location, f"{fraction_label} sum is {total:.6f}; result is unavailable"))
            return {}, tuple(issues)

        if any(value < 0 for value in fractions.values()):
            issues.append(_warning(location, f"{fraction_label} contains negative values; result is unavailable"))
            return {}, tuple(issues)

        normalized = dict(fractions)
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            issues.append(_warning(location, f"{fraction_label} sums to {total:.6f}; normalizing before derivation"))
            normalized = {key: value / total for key, value in fractions.items()}

        return normalized, tuple(issues)
