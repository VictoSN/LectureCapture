from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer
from sumy.nlp.stemmers import Stemmer

LANGUAGE = "english"

def summarize(text: str, sentences: int = 5) -> str:
    summary = ""
    parser = PlaintextParser.from_string(text, Tokenizer(LANGUAGE))
    stemmer = Stemmer(LANGUAGE)
    summarizer = LsaSummarizer(stemmer)
    
    for sentence in summarizer(parser.document, sentences):
        summary += str(sentence) + "\n"
    
    return summary