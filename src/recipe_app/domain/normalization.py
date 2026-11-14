"""Ingredient-name normalization (ADR-0001 rule 4)."""

import re
import unicodedata


def normalize(text: str) -> str:
    """Return the canonical form of an ingredient name for comparison and search.

    Applies, in order (docs/adr/0001-ingredient-normalization.md, rule 4):

    1. Unicode NFKC: full-width letters, ligatures and Unicode spaces
       become their plain equivalents.
    2. Trim leading and trailing whitespace.
    3. Collapse every run of whitespace to one space, which also catches
       the whitespace NFKC leaves alone (tab, newline, U+2028).
    4. casefold(), which is stronger than lower() ("Stra\\u00dfe" -> "strasse").
    5. NFKC again, because casefold() can return text that is no longer
       NFKC ("\\u01f0" casefolds to "j" + U+030C).
    """
    result = unicodedata.normalize("NFKC", text)
    result = result.strip()
    result = " ".join(result.split())
    result = result.casefold()

    return unicodedata.normalize("NFKC", result)


def search_key(text: str) -> str:
    """Normalized, without accents, and with punctuation and underscores
    folded to single spaces: "Crème brûlée" -> "creme brulee", "Peri-peri" ->
    "peri peri". Recipe search compares these (ADR-0012 rule 10). Ingredient
    names keep their accents (ADR-0001); only search drops them, because a
    phone keyboard adds them to words the book spells without.
    """
    decomposed = unicodedata.normalize("NFKD", normalize(text))
    bare = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    folded = unicodedata.normalize("NFKC", bare)
    return " ".join(re.sub(r"[\W_]+", " ", folded).split())
