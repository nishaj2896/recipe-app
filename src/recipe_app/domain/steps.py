"""What a recipe step mentions: catalog ingredients and amounts (ADR-0008 rule 4)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.normalization import normalize
from recipe_app.domain.units import Unit, UnitKind

_WORD = re.compile(r"[^\W_]+")

# NFKC turns "½" into 1, U+2044 FRACTION SLASH, 2, so slash fractions cover it too.
_NUMBER = (
    r"(?:\d+(?:[.,]\d+)?(?:\s*[/\u2044]\s*\d+)?"
    r"|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|half)"
)


def _forms(units: list[Unit]) -> str:
    forms = {form for unit in units for form in (unit.value, unit.plural)}
    # Longest first, so "cups" is tried before "cup".
    return "|".join(re.escape(form) for form in sorted(forms, key=len, reverse=True))


_ALL_UNITS = _forms(list(Unit))
_ARTICLE_UNITS = _forms([unit for unit in Unit if unit.kind is not UnitKind.PRODUCE])
_AMOUNT = re.compile(
    rf"(?<![\w.]){_NUMBER}\s*(?:of\s+)?(?:{_ALL_UNITS})(?!\w)"
    rf"|(?<!\w)(?:a|an)\s+(?:{_ARTICLE_UNITS})(?!\w)"
)


def states_amount(step: str) -> str | None:
    """The first amount a step writes out ("2 cups", "½ tsp", "a pinch"), if any."""
    found = _AMOUNT.search(normalize(step))
    return found.group(0) if found else None


@dataclass(frozen=True, slots=True)
class StepMatcher:
    """Finds the catalog ingredients a step names; build it with step_matcher.

    `phrases` maps each phrase's words to its ingredient id, grouped by the
    phrase's first word and sorted longest first.
    """

    phrases: Mapping[str, tuple[tuple[tuple[str, ...], str], ...]]

    def mentions(self, step: str) -> list[str]:
        """Ingredient ids in the order the step names them, repeats included.

        One left-to-right scan: at each word the longest phrase that matches
        there wins and the scan continues after it, so matches never overlap
        and "coconut milk" is coconut milk, not coconut and milk.
        """
        words = _WORD.findall(normalize(step))
        found: list[str] = []
        position = 0
        while position < len(words):
            for phrase, ingredient_id in self.phrases.get(words[position], ()):
                if tuple(words[position : position + len(phrase)]) == phrase:
                    found.append(ingredient_id)
                    position += len(phrase)
                    break
            else:
                position += 1
        return found


def step_matcher(catalog: IngredientCatalog) -> StepMatcher:
    """Every live ingredient's name and search terms, plus their plurals.

    A phrase also matches with its last word in the regular English plural
    ("potatoes", "eggs", "cherries"), unless that form is already another
    ingredient's phrase.
    """
    exact: dict[tuple[str, ...], str] = {}
    for item in catalog.by_id.values():
        if item.retired:
            continue
        for text in (item.name, *item.search_terms):
            words = tuple(_WORD.findall(normalize(text)))
            if words:
                exact.setdefault(words, item.id)
    phrases = dict(exact)
    for words, ingredient_id in exact.items():
        for plural in _plurals(words[-1]):
            phrases.setdefault((*words[:-1], plural), ingredient_id)

    grouped: dict[str, list[tuple[tuple[str, ...], str]]] = {}
    for words, ingredient_id in phrases.items():
        grouped.setdefault(words[0], []).append((words, ingredient_id))
    return StepMatcher(
        phrases=MappingProxyType(
            {
                first: tuple(sorted(entries, key=lambda entry: -len(entry[0])))
                for first, entries in grouped.items()
            }
        )
    )


def _plurals(word: str) -> tuple[str, ...]:
    if not word.isalpha() or word.endswith("s"):
        return ()
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return (word[:-1] + "ies",)
    if word.endswith(("ch", "sh", "x", "o")):
        return (word + "es", word + "s")
    return (word + "s",)
