"""Typed errors. Messages are safe to show to clients; they never carry document content."""


class AccessLensError(Exception):
    """Base class; ``code`` is the stable problem+json type, ``status`` the HTTP status."""

    code = "error"
    status = 500
    default_message = "An internal error occurred."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.default_message)


class InvalidFileError(AccessLensError):
    code = "invalid_file"
    status = 400
    default_message = "The file is not a valid Word (.docx) or PowerPoint (.pptx) document."


class FileTooLargeError(AccessLensError):
    code = "file_too_large"
    status = 413
    default_message = "The file exceeds the maximum upload size."


class MacroEnabledError(AccessLensError):
    code = "macro_enabled"
    status = 422
    default_message = "Macro-enabled documents are not accepted."


class UnauthorizedError(AccessLensError):
    code = "unauthorized"
    status = 401
    default_message = "A valid API key is required."


class RateLimitedError(AccessLensError):
    code = "rate_limited"
    status = 429
    default_message = "Too many requests. Try again later."


class InvalidRequestError(AccessLensError):
    code = "invalid_request"
    status = 400
    default_message = "The request is not valid."


class LlmUnavailableError(AccessLensError):
    """Internal: the LLM layer cannot be used. Audits degrade to rules-only instead of failing."""

    code = "llm_unavailable"
    status = 503
    default_message = "AI review is unavailable."


class ParseFailedError(AccessLensError):
    code = "parse_failed"
    status = 422
    default_message = "The document could not be parsed."
