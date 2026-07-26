# One-shot, quality-first tasks (summary, translate / define, quiz).
MODEL_CHAIN = [
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite",
]

# Lead with the highest-daily-allowance model for frequent per-chunk tasks, then fall back.
FREQUENT_MODEL_CHAIN = [
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3.5-flash",
]


# Every model the app might use (both chains, de-duplicated, preferred order first).
ALL_MODELS = list(dict.fromkeys(MODEL_CHAIN + FREQUENT_MODEL_CHAIN))

# Published free-tier requests-per-day per model (reference, not live quota).
FREE_TIER_RPD = {
    "gemini-2.5-flash": 20,
    "gemini-2.5-flash-lite": 20,
    "gemini-3.1-flash-lite-preview": 500,
    "gemini-3.5-flash": 20,
}


def probe_model(api_key: str, model: str) -> tuple[str, str]:
    """Ping one model. Returns (status, detail)."""
    try:
        generate(api_key, "ping", chain=[model])
        return "ok", ""
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        text = detail.lower()
        if any(k in text for k in ("api key not valid", "api_key_invalid", "unauthenticated",
                                   "permission_denied", "unauthorized", " 401", " 403")):
            return "invalid_key", detail
        if any(k in text for k in ("429", "resource_exhausted", "rate limit", "quota", "exceed")):
            return "limited", detail
        if any(k in text for k in ("404", "not found", "not_found")):
            return "missing", detail
        # 503/overload is transient; server is busy but key is valid.
        if any(k in text for k in ("503", "unavailable", "overloaded", "high demand", "try again")):
            return "busy", detail
        print(f"[API Test] {model} error: {detail}")
        return "error", detail


def pretty_model(model_id: str) -> str:
    """Human-readable model name, e.g. 'gemini-3.1-flash-lite-preview' → 'Gemini 3.1 Flash Lite'."""
    if not model_id:
        return "Gemini"
    name = model_id.replace("gemini-", "").replace("-preview", "")
    return "Gemini " + " ".join(part.capitalize() for part in name.split("-"))


def _should_try_next(exc: Exception) -> bool:
    """True for rate-limit, quota, unavailable model, or transient overload."""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(k in text for k in (
        "429", "resource_exhausted", "rate limit", "quota", "exceed",
        "404", "not found", "not_found", "unavailable", "503", "overloaded",
        "500", "internal",
    ))


# Cache one client per API key so per-chunk tasks don't rebuild it each time.
_clients: dict = {}


def _client(api_key: str):
    client = _clients.get(api_key)
    if client is None:
        from google import genai
        client = genai.Client(api_key=api_key)
        _clients[api_key] = client
    return client


def generate(api_key: str, contents, config=None, chain=None, on_attempt=None):
    """generate_content with model fallback. Returns (response, model_id) for the first
    successful model; raises the last error if every model fails. `on_attempt` is called
    before each model for progress reporting."""
    client = _client(api_key)
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
