import re

from PyQt6.QtCore import QThread, pyqtSignal

# Summarization is Gemini-only, the same as Quiz / Translate / Define. The previous
# on-device sumy fallback was removed (Issue #6): it pulled in nltk + requests + urllib3
# for a markedly lower-quality extractive summary, and the app already standardises every
# other "understanding" feature on the Gemini API. OCR and speech keep their local engines;
# summarization does not.


def strip_code_fence(text: str) -> str:
    """Unwrap a Markdown code fence that surrounds the ENTIRE text. Models often wrap
    their whole answer in ```markdown ... ``` despite being told not to; rendered as
    Markdown that becomes one literal code block (every ## and ** shown raw), so strip
    it. Only unwraps a single all-enclosing fence — content with inner code blocks is
    left untouched."""
    if not text:
        return text
    lines = text.strip().splitlines()
    fences = [i for i, ln in enumerate(lines) if ln.strip().startswith("```")]
    if (len(fences) == 2 and fences[0] == 0 and fences[1] == len(lines) - 1
            and re.fullmatch(r"```[a-zA-Z0-9_+-]*", lines[0].strip())
            and lines[-1].strip() == "```"):
        return "\n".join(lines[1:-1]).strip()
    return text

def summarize_api(text: str, api_key: str) -> tuple[str, str]:
    """Returns (summary_text, model_id)."""
    from core.gemini import generate
    response, model = generate(
        api_key,
        "Summarize the following lecture notes using markdown formatting. "
        "Use ## for section headings, - for bullet points, and **bold** for key terms. "
        "Preserve all key concepts, definitions, and important details. "
        "Return only the markdown, no preamble.\n\n"
        f"{text}"
    )
    return strip_code_fence(response.text), model

def summarize(text: str, api_key: str = "") -> tuple[str, str]:
    """
    Returns (summary_text, engine_name).
    Gemini-only: a key is required. Raises ValueError when none is supplied so the
    caller can surface the same "Gemini API key needed" prompt as Quiz / Translate.
    """
    if not api_key:
        raise ValueError("A Gemini API key is required to summarize.")
    from core.gemini import pretty_model
    summary, model = summarize_api(text, api_key)
    return summary, pretty_model(model)


class SummarizeWorker(QThread):
    """Runs summarize() off the GUI thread. The Gemini call can take several
    seconds; doing it inline blocks Qt's event loop and freezes the whole app."""
    done = pyqtSignal(str, str)   # (summary_text, engine_name)
    failed = pyqtSignal(str)      # error message

    def __init__(self, text: str, api_key: str = "") -> None:
        super().__init__()
        self._text = text
        self._api_key = api_key

    def run(self) -> None:
        try:
            summary, engine = summarize(self._text, self._api_key)
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.done.emit(summary or "", engine)
