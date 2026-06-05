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
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": (
                "Summarize the following lecture notes into clear, concise bullet points. "
                "Preserve all key concepts, definitions, and important details.\n\n"
                f"{text}"
            )
        }]
    )
    return response.content[0].text

def summarize(text: str, sentences: int = 5, api_key: str = "") -> tuple[str, str]:
    """
    Returns (summary_text, engine_name).
    Uses Claude API if api_key is provided, otherwise falls back to local sumy.
    """
    if api_key:
        try:
            return summarize_api(text, api_key), "claude-haiku"
        except Exception as e:
            print(f"[Summarizer] API failed, falling back to local: {e}")
    return summarize_local(text, sentences), "sumy"
