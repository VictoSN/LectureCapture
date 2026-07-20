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
    # Not an API failure: loopback wasn't available, fell back to mic.
    "mic_fallback": "No loopback device. Recording the microphone instead",
}


def status_message(status: str) -> str:
    """Longer, friendly sentence for dialogs and the translate/define popup."""
    return {
        "no_key": "No API key. Add a Gemini API key in Settings.",
        "invalid_key": "Invalid API key. Check your Gemini API key in Settings.",
        "no_connection": "No connection. Check your internet and try again.",
    }.get(status, "Something went wrong. Please try again.")
