import re

from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.nlp.stemmers import Stemmer

from PyQt6.QtCore import QThread, pyqtSignal

LANGUAGE = "english"


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

def summarize_local(text: str, sentences: int = 5) -> str:
    summary = ""
    parser = PlaintextParser.from_string(text, Tokenizer(LANGUAGE))
    stemmer = Stemmer(LANGUAGE)
    summarizer = LsaSummarizer(stemmer)
    for sentence in summarizer(parser.document, sentences):
        summary += str(sentence) + "\n"
    return summary

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

def summarize(text: str, sentences: int = 5, api_key: str = "") -> tuple[str, str]:
    """
    Returns (summary_text, engine_name).
    Uses Gemini API if api_key is provided, otherwise falls back to local sumy.
    """
    if api_key:
        try:
            from core.gemini import pretty_model
            summary, model = summarize_api(text, api_key)
            return summary, pretty_model(model)
        except Exception as e:
            print(f"[Summarizer] API failed, falling back to local: {e}")
    return summarize_local(text, sentences), "sumy"


class SummarizeWorker(QThread):
    """Runs summarize() off the GUI thread. The Gemini call can take several
    seconds; doing it inline blocks Qt's event loop and freezes the whole app."""
    done = pyqtSignal(str, str)   # (summary_text, engine_name)
    failed = pyqtSignal(str)      # error message

    def __init__(self, text: str, sentences: int = 5, api_key: str = "") -> None:
        super().__init__()
        self._text = text
        self._sentences = sentences
        self._api_key = api_key

    def run(self) -> None:
        try:
            summary, engine = summarize(self._text, self._sentences, self._api_key)
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.done.emit(summary or "", engine)
