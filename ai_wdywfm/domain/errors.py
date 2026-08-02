class WdywfmError(Exception):
    """Base error safe to present in the UI."""

    error_category = "internal"

    def __init__(self, message: str, *, category: str | None = None) -> None:
        super().__init__(message)
        if category is not None:
            self.error_category = category


class ValidationError(WdywfmError):
    """A provider response does not satisfy the v1 contract."""

    error_category = "invalid_response"


class ProviderError(WdywfmError):
    """A provider request failed or returned an unusable response."""

    error_category = "provider_unavailable"


class RecommenderError(WdywfmError):
    """The optional CivitAI recommender could not return results."""

    error_category = "civitai_offline"


def error_category(error: BaseException) -> str:
    """Return the stable, user-facing diagnostics category for an exception."""
    category = getattr(error, "error_category", None)
    if isinstance(category, str) and category:
        return category
    return "internal"
