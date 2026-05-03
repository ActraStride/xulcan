# tests/utils/unicode.py
import unicodedata

def unicode_semantic_eq(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        return unicodedata.normalize("NFKC", s).casefold()
    return norm(a) == norm(b)
