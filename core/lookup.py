"""On-demand Gemini lookups for selected transcript text: translate or define.

Runs off the GUI thread (the API call takes a second or two). One call per request
— this is user-initiated, not per-chunk, so it's easy on free-tier rate limits.
"""

from PyQt6.QtCore import QThread, pyqtSignal


class LookupWorker(QThread):
    done = pyqtSignal(str)     # result text
    failed = pyqtSignal(str)   # error message

    def __init__(self, text: str, kind: str, target: str, api_key: str) -> None:
        super().__init__()
        self._text = text
        self._kind = kind        # "translate" | "define"
        self._target = target    # language (translate only)
        self._api_key = api_key

    def run(self) -> None:
        try:
            result = self._lookup()
        except Exception as e:
            from core.api_errors import classify_api_error, status_message
            status = classify_api_error(e)
            self.failed.emit(status_message(status) if status != "other" else str(e))
            return
        self.done.emit(result or "")

    def _lookup(self) -> str:
        from google import genai
        client = genai.Client(api_key=self._api_key)
        if self._kind == "translate":
            prompt = (
                f"Translate the following text to {self._target}. "
                "Return only the translation — no preamble, notes, or quotation marks:\n\n"
                f"{self._text}"
            )
        else:
            prompt = (
                f'Define the term or phrase "{self._text}" concisely and clearly, as it '
                "would be understood in an academic or lecture context. Use 1-3 sentences. "
                "Plain text, no preamble."
            )
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return (response.text or "").strip()
