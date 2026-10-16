import json
import string
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [pytest.param(case["input"], case["expected"], id=case["id"]) for case in CASES],
)
def test_normalize(text: str, expected: str):
    assert normalize(text) == expected


@given(st.text())
def test_normalize_is_idempotent(s: str) -> None:
    once = normalize(s)
    assert normalize(once) == once


@given(st.text())
def test_normalize_has_no_outer_whitespace(s: str) -> None:
    result = normalize(s)
    assert result == result.strip()


@given(st.text())
def test_normalize_uses_only_single_plain_spaces(s: str) -> None:
    result = normalize(s)
    assert "  " not in result
    assert all(ch == " " or not ch.isspace() for ch in result)


@given(st.text())
def test_normalize_output_is_nfkc(s: str) -> None:
    assert unicodedata.is_normalized("NFKC", normalize(s))


@pytest.mark.parametrize("form", FORMS)
@given(st.text())
def test_normalize_ignores_unicode_form(form: NormalForm, s: str) -> None:
    assert normalize(unicodedata.normalize(form, s)) == normalize(s)


@given(st.text(), WHITESPACE, WHITESPACE)
def test_normalize_ignores_outer_whitespace(s: str, before: str, after: str) -> None:
    assert normalize(before + s + after) == normalize(s)


@given(st.text(), WHITESPACE)
def test_normalize_treats_any_whitespace_run_as_one_space(s: str, run: str) -> None:
    assert normalize(s.replace(" ", run)) == normalize(s)


@given(ASCII_WORDS)
def test_normalize_matches_simple_model_on_ascii(s: str) -> None:
    assert normalize(s) == " ".join(s.lower().split())
