from __future__ import annotations


class LogbookError(Exception):
    """Base error for the mouse_logbook package."""


class LogbookFormatError(LogbookError):
    """Raised when the logbook file structure/columns do not match the expected format."""


class ProjectNotFoundError(LogbookError):
    """Raised when a project/proposal sheet could not be located."""


class ProjectSheetFormatError(LogbookError):
    """Raised when a project/proposal sheet does not match the expected schema."""


class SampleNotFoundError(LogbookError):
    """Raised when a sample ID referenced in the logbook cannot be found in the project sheet."""


class SampleEnvironmentNotFoundError(LogbookError):
    """Raised when a sampos cannot be found in the Sample Environments sheet."""


class SampleEnvironmentFormatError(LogbookError):
    """Raised when the Sample Environments sheet does not match the expected schema."""
