class WdywfmError(Exception):
    """Base error safe to present in the UI."""


class ValidationError(WdywfmError):
    """A provider response does not satisfy the v1 contract."""


class ProviderError(WdywfmError):
    """A provider request failed or returned an unusable response."""
