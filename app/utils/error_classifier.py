"""
Error Classifier

Not all errors are equal. This classifier tells us:
- Is the error transient? (network blip, rate limit) → client should retry
- Is it a provider error? (Gemini/Bedrock down) → different message
- Is it a client error? (bad input) → 400, don't retry
- Is it our bug? (unhandled exception) → 500, investigate

This classification drives:
1. What HTTP status code to return
2. What message to show the client
3. Whether to suggest retrying
4. How urgently to alert the team
"""
from dataclasses import dataclass
from typing import Type


@dataclass
class ErrorClassification:
    """Result of classifying an exception."""
    error_type: str          # Class name of the exception
    http_status_code: int    # What HTTP status to return
    is_transient: bool       # Should the client retry?
    is_provider_error: bool  # Is it a LLM/external API error?
    is_client_error: bool    # Is it the client's fault?
    user_message: str        # Safe message to show the user
    log_level: str           # How urgently to log this


# Patterns that indicate a transient (temporary) error
_TRANSIENT_PATTERNS = [
    "timeout",
    "rate limit",
    "rate_limit",
    "429",
    "503",
    "502",
    "connection",
    "throttl",
    "too many requests",
    "temporarily unavailable",
    "service unavailable",
    "try again",
]

# Patterns that indicate an LLM/external API provider error
_PROVIDER_PATTERNS = [
    "gemini",
    "generativeai",
    "bedrock",
    "anthropic",
    "google",
    "aws",
    "api key",
    "invalid api",
    "quota exceeded",
]

# Exception types that are always the client's fault
_CLIENT_ERROR_TYPES: tuple[Type[Exception], ...] = (
    ValueError,
    TypeError,
    KeyError,
)


def classify_error(exc: Exception) -> ErrorClassification:
    """
    Classify an exception and return structured information about it.

    Usage:
        try:
            result = await llm.generate(...)
        except Exception as e:
            classification = classify_error(e)
            return JSONResponse(
                status_code=classification.http_status_code,
                content={"error": classification.user_message}
            )
    """
    error_str = str(exc).lower()
    error_type = type(exc).__name__

    # Check patterns
    is_transient = any(p in error_str for p in _TRANSIENT_PATTERNS)
    is_provider = any(p in error_str for p in _PROVIDER_PATTERNS)
    is_client = isinstance(exc, _CLIENT_ERROR_TYPES)

    # Determine HTTP status code
    if is_client:
        status_code = 400
    elif is_transient:
        status_code = 503
    elif is_provider:
        status_code = 502
    else:
        status_code = 500

    # Determine log level
    if is_client:
        log_level = "warning"
    elif is_transient:
        log_level = "warning"
    else:
        log_level = "error"

    # Determine user-safe message
    if is_client:
        user_message = f"Invalid request: {str(exc)}"
    elif is_transient:
        user_message = (
            "The service is temporarily unavailable. "
            "Please try again in a few seconds."
        )
    elif is_provider:
        user_message = (
            "The AI provider is currently unavailable. "
            "Please try again shortly."
        )
    else:
        user_message = (
            "An unexpected error occurred. "
            "Please try again or contact support."
        )

    return ErrorClassification(
        error_type=error_type,
        http_status_code=status_code,
        is_transient=is_transient,
        is_provider_error=is_provider,
        is_client_error=is_client,
        user_message=user_message,
        log_level=log_level,
    )