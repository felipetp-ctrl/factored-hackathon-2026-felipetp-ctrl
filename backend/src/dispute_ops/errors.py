class AccessDenied(Exception):
    """Resource exists but does not belong to the session's customer."""


class NotFound(Exception):
    """Resource does not exist."""


class ToolUnavailable(Exception):
    """Transient tool failure; safe to retry."""
