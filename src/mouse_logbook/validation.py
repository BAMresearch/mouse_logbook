from __future__ import annotations

from typing import Generic, Literal, TypeVar

import attrs

ValidationSeverity = Literal["error", "warning", "info"]

T = TypeVar("T")


@attrs.frozen(kw_only=True, slots=True)
class ValidationIssue:
    severity: ValidationSeverity
    location: str
    message: str

    def __str__(self) -> str:
        if self.location:
            return f"{self.location}: {self.message}"
        return self.message


@attrs.frozen(kw_only=True, slots=True)
class ValidationReport(Generic[T]):
    value: T
    issues: tuple[ValidationIssue, ...] = attrs.field(factory=tuple)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    def issues_for(self, severity: ValidationSeverity) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == severity)
