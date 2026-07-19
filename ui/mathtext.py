import re
from pylatexenc.latex2text import LatexNodes2Text

# The OCR vision model returns math wrapped in LaTeX ($...$ inline, $$...$$ display).
# Tesseract can't read math at all, so the LaTeX is the only faithful transcription
# we have. Here we convert just those math spans to Unicode (∈, ℕ, ⊕, ∫, ², ₙ …) for
# display, so the panel shows readable symbols instead of raw "\in \mathbb{N}" / "G_n".

_converter = LatexNodes2Text()

# Unicode super/subscript tables. pylatexenc leaves ^ and _ as literal characters
# (and strips the grouping braces), so we map them ourselves *before* handing the
# rest to pylatexenc. Characters that map to themselves (*, †, ′) have no raised
# Unicode form — baseline is the conventional plain-text rendering (e.g. C*-algebra).
_SUPERSCRIPTS = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷",
    "8": "⁸", "9": "⁹", "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ", "g": "ᵍ", "h": "ʰ",
    "i": "ⁱ", "j": "ʲ", "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ", "p": "ᵖ",
    "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ", "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ",
    "z": "ᶻ", "*": "*", "†": "†", "′": "′",
}
_SUBSCRIPTS = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇",
    "8": "₈", "9": "₉", "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ", "m": "ₘ",
    "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ",
    "x": "ₓ",
}

# Operand commands that appear inside ^/_. Normalise to a single glyph first so the
# super/subscript pass can handle them (e.g. the * in a C^\ast-algebra).
_OPERAND_COMMANDS = {r"\ast": "*", r"\dagger": "†", r"\dag": "†", r"\prime": "′"}

_BRACED = re.compile(r"([_^])\{([^{}]+)\}")       # ^{2n}, _{ij}
_SINGLE = re.compile(r"([_^])([^\s\\{}])")          # ^2, _n, ^* (single token)
_DISPLAY_MATH = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_MATH = re.compile(r"\$([^$\n]+?)\$")


def _to_script(content: str, table: dict) -> "str | None":
    out = []
    for ch in content:
        if ch in table:
            out.append(table[ch])
        elif ch.isspace():
            continue
        else:
            return None  # any unmappable char => leave the whole group as-is
    return "".join(out)


def _apply_scripts(latex: str) -> str:
    for cmd, glyph in _OPERAND_COMMANDS.items():
        latex = latex.replace(cmd, glyph)

    def repl(m: "re.Match") -> str:
        table = _SUPERSCRIPTS if m.group(1) == "^" else _SUBSCRIPTS
        mapped = _to_script(m.group(2), table)
        return mapped if mapped is not None else m.group(0)

    latex = _BRACED.sub(repl, latex)   # multi-char groups first (braces intact)
    latex = _SINGLE.sub(repl, latex)   # then single-token scripts
    return latex


def _convert(match: "re.Match") -> str:
    try:
        # Super/subscripts first (needs the braces pylatexenc would strip), then let
        # pylatexenc handle the symbol commands (\in, \mathbb, \bigoplus, …).
        inner = _apply_scripts(match.group(1))
        return _converter.latex_to_text(inner).strip()
    except Exception:
        return match.group(0)  # leave the original LaTeX untouched if it won't parse


def render_math(text: str) -> str:
    """Replace inline ($...$) and display ($$...$$) LaTeX math with Unicode symbols.

    Only the math spans are converted; the surrounding prose is left byte-for-byte,
    so a literal % / & / # in normal slide text is never swallowed as LaTeX syntax.
    Idempotent: converted text has no $ spans left, so re-running is a no-op.
    """
    if not text or "$" not in text:
        return text
    text = _DISPLAY_MATH.sub(_convert, text)
    text = _INLINE_MATH.sub(_convert, text)
    return text
