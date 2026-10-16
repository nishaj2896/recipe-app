import json
import string
import sys
import unicodedata
from pathlib import Path
from typing import Literal, TypedDict

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recipe_app.domain.normalization import normalize


class Case(TypedDict):
    id: str
    input: str
    expected: str
    why: str


FIXTURE = Path(__file__).parent.parent / "fixtures" / "normalization_cases.json"
CASES: list[Case] = json.loads(FIXTURE.read_text(encoding="utf-8"))

NormalForm = Literal["NFC", "NFD", "NFKC", "NFKD"]
FORMS: tuple[NormalForm, ...] = ("NFC", "NFD", "NFKC", "NFKD")

# st.text() rarely generates whitespace, so these strategies target it directly.
WHITESPACE = st.text(
    alphabet=" \t\n\r" + chr(0x00A0) + chr(0x2003) + chr(0x3000) + chr(0x2028),
    min_size=1,
)
ASCII_WORDS = st.text(alphabet=string.ascii_letters + " \t\n")
CASEFOLD_BREAKS_NFKC = [
    c
    for c in map(chr, range(sys.maxunicode + 1))
    if c.casefold() != c
    and not unicodedata.is_normalized(
        "NFKC", unicodedata.normalize("NFKC", c).casefold()
    )
]
TEXT_WITH_CASEFOLD_TRAPS = st.text() | st.lists(
    st.sampled_from(CASEFOLD_BREAKS_NFKC) | st.characters()
).map("".join)


@pytest.mark.parametrize(
    ("text", "expected"),
    [pytest.param(case["input"], case["expected"], id=case["id"]) for case in CASES],
)
def test_normalize(text: str, expected: str) -> None:
    """Each fixture case gives its expected value; the app reuses these cases."""
    assert normalize(text) == expected


@given(st.text())
def test_normalize_is_idempotent(s: str) -> None:
    """Normalizing twice changes nothing, so stored names re-normalize safely."""
    once = normalize(s)
    assert normalize(once) == once


@given(st.text())
def test_normalize_has_no_outer_whitespace(s: str) -> None:
    """No outer whitespace survives, so "tomato " can't become a duplicate."""
    result = normalize(s)
    assert result == result.strip()


@given(st.text())
def test_normalize_uses_only_single_plain_spaces(s: str) -> None:
    """Words are separated by exactly one ASCII space, never tabs or Unicode spaces."""
    result = normalize(s)
    assert "  " not in result
    assert all(ch == " " or not ch.isspace() for ch in result)


@given(TEXT_WITH_CASEFOLD_TRAPS)
def test_normalize_output_is_nfkc(s: str) -> None:
    """The result is NFKC, which proves step 5 re-normalizes what casefold() breaks."""
    assert unicodedata.is_normalized("NFKC", normalize(s))


@pytest.mark.parametrize("form", FORMS)
@given(st.text())
def test_normalize_ignores_unicode_form(form: NormalForm, s: str) -> None:
    """Text that looks the same normalizes the same, however it is encoded."""
    assert normalize(unicodedata.normalize(form, s)) == normalize(s)


@given(st.text(), WHITESPACE, WHITESPACE)
def test_normalize_ignores_outer_whitespace(s: str, before: str, after: str) -> None:
    """Padding with any whitespace, Unicode spaces included, changes nothing."""
    assert normalize(before + s + after) == normalize(s)


@given(st.text(), WHITESPACE)
def test_normalize_treats_any_whitespace_run_as_one_space(s: str, run: str) -> None:
    """Any run of whitespace between words counts the same as one space."""
    assert normalize(s.replace(" ", run)) == normalize(s)


@given(ASCII_WORDS)
def test_normalize_matches_simple_model_on_ascii(s: str) -> None:
    """On plain ASCII, normalize agrees with lower() plus collapsing whitespace."""
    assert normalize(s) == " ".join(s.lower().split())
