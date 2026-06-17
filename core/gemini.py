"""Central Gemini generation with model fallback.

The free tier caps each model with tight per-minute and per-day limits, and a single
model can be exhausted mid-session. So rather than calling one fixed model, we walk a
chain and transparently move to the next model when the current one is rate-limited,
exhausted, unknown, or temporarily overloaded. Auth and bad-request failures are NOT
retried — they'd fail identically on every model, so we surface them immediately.

Note: the "Live API" models (Native Audio Dialog, Live, Live Translate) are a separate
streaming/WebSocket API for real-time voice conversation, not a drop-in for these
request/response generate_content calls, so they aren't part of these chains.
"""


# One-shot, quality-first tasks (summary, translate / define, quiz).
MODEL_CHAIN = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash",
    "gemini-3.5-flash",
]

# Per-chunk / per-slide tasks (live speech, OCR) that fire many times during a recording
# — lead with the model that has the largest daily allowance so a long session is less
# likely to exhaust it, then fall back to the rest.
FREQUENT_MODEL_CHAIN = [
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3-flash",
    "gemini-3.5-flash",
]


# Every model the app might use (both chains, de-duplicated, preferred order first).
ALL_MODELS = list(dict.fromkeys(MODEL_CHAIN + FREQUENT_MODEL_CHAIN))

# Published free-tier requests-per-day per model (the API doesn't expose live remaining
# quota, so this is a static reference shown alongside the live availability check).
FREE_TIER_RPD = {
    "gemini-2.5-flash": 20,
    "gemini-2.5-flash-lite": 20,
    "gemini-3.1-flash-lite-preview": 500,
    "gemini-3-flash": 20,
    "gemini-3.5-flash": 20,
}


def probe_model(api_key: str, model: str) -> str:
    """Ping a single model. Returns 'ok' | 'limited' | 'missing' | 'invalid_key' | 'error'."""
    from google import genai
    try:
        genai.Client(api_key=api_key).models.generate_content(model=model, contents="ping")
        return "ok"
    except Exception as e:
        text = f"{type(e).__name__} {e}".lower()
        if any(k in text for k in ("api key not valid", "api_key_invalid", "unauthenticated",
                                   "permission_denied", "unauthorized", " 401", " 403")):
            return "invalid_key"
        if any(k in text for k in ("429", "resource_exhausted", "rate limit", "quota", "exceed")):
            return "limited"
        if any(k in text for k in ("404", "not found", "not_found")):
            return "missing"
        return "error"


def pretty_model(model_id: str) -> str:
    """Human-readable model name, e.g. 'gemini-3.1-flash-lite-preview' → 'Gemini 3.1 Flash Lite'."""
    if not model_id:
        return "Gemini"
    name = model_id.replace("gemini-", "").replace("-preview", "")
    return "Gemini " + " ".join(part.capitalize() for part in name.split("-"))


def _should_try_next(exc: Exception) -> bool:
    """A failure worth retrying on a different model: rate-limit / quota exhaustion, an
    unknown or unavailable model, or a transient overload. (Auth / bad-request are not —
    they'd fail on every model.)"""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(k in text for k in (
        "429", "resource_exhausted", "rate limit", "quota", "exceed",
        "404", "not found", "not_found", "unavailable", "503", "overloaded",
        "500", "internal",
    ))


def generate(api_key: str, contents, config=None, chain=None, on_attempt=None):
    """generate_content with model fallback. Returns (response, model_id) for the first
    model that succeeds; raises the last error if every model in the chain fails.
    `on_attempt(model_id)` is called before each model is tried (used to show progress)."""
    from google import genai
    client = genai.Client(api_key=api_key)
    last_exc = None
    for model in (chain or MODEL_CHAIN):
        if on_attempt:
            on_attempt(model)
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            return response, model
        except Exception as e:
            last_exc = e
            if _should_try_next(e):
                print(f"[Gemini] {model} unavailable ({type(e).__name__}); trying next model")
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("No Gemini model configured")
