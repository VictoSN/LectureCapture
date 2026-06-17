"""Best-effort classification of Gemini API failures into a short status the UI can
show ("No connection" / "Invalid API key"). We match on the exception text because
the google-genai client raises several different exception types for what is, to the
user, the same problem.
"""


def classify_api_error(exc: Exception) -> str:
    """Returns 'invalid_key', 'no_connection', or 'other'."""
    text = f"{type(exc).__name__} {exc}".lower()
    if any(k in text for k in (
        "api key not valid", "api_key_invalid", "invalid api key",
        "permission_denied", "permission denied", "unauthenticated",
        "unauthorized", " 401", " 403",
    )):
        return "invalid_key"
    if any(k in text for k in (
        "connection", "connecterror", "getaddrinfo", "name or service not known",
        "temporary failure in name resolution", "failed to establish", "max retries",
        "timed out", "timeout", "network", "unreachable", "ssl",
        "no address associated", "11001", "[errno",
    )):
        return "no_connection"
    return "other"


# Compact labels for the recording-time banner.
SHORT_STATUS = {
    "no_key": "No API key",
    "invalid_key": "Invalid API key",
    "no_connection": "No connection",
}


def status_message(status: str) -> str:
    """Longer, friendly sentence for dialogs and the translate/define popup."""
    return {
        "no_key": "No API key — add a Gemini API key in Settings.",
        "invalid_key": "Invalid API key — check your Gemini API key in Settings.",
        "no_connection": "No connection — check your internet and try again.",
    }.get(status, "Something went wrong. Please try again.")
