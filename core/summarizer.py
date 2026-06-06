from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.nlp.stemmers import Stemmer

LANGUAGE = "english"

def summarize_local(text: str, sentences: int = 5) -> str:
    summary = ""
    parser = PlaintextParser.from_string(text, Tokenizer(LANGUAGE))
    stemmer = Stemmer(LANGUAGE)
    summarizer = LsaSummarizer(stemmer)
    for sentence in summarizer(parser.document, sentences):
        summary += str(sentence) + "\n"
    return summary

def summarize_api(text: str, api_key: str) -> str:
    from google import genai
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=(
            "Summarize the following lecture notes using markdown formatting. "
            "Use ## for section headings, - for bullet points, and **bold** for key terms. "
            "Preserve all key concepts, definitions, and important details. "
            "Return only the markdown, no preamble.\n\n"
            f"{text}"
        )
    )
    return response.text

def summarize(text: str, sentences: int = 5, api_key: str = "") -> tuple[str, str]:
    """
    Returns (summary_text, engine_name).
    Uses Gemini API if api_key is provided, otherwise falls back to local sumy.
    """
    if api_key:
        try:
            return summarize_api(text, api_key), "gemini-flash"
        except Exception as e:
            print(f"[Summarizer] API failed, falling back to local: {e}")
    return summarize_local(text, sentences), "sumy"
