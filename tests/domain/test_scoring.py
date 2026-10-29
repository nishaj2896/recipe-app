from collections.abc import Callable

import pytest

from recipe_app.domain.scoring import (
    EXCLUDED_STAPLE,
    MAIN,
    SCORING_VERSION,
    SUPPORTING,
    match_tenths,
    score_int,
    score_triangle,
)

# One row per SCORING_VERSION. Add a row when you bump; never edit an old one.
SCORING_FINGERPRINTS: dict[int, dict[str, object]] = {
    1: {
        "weights": (4, 2, 1),
        "score_int": {(4, 4): 301030, (6, 6): 397940, (14, 16): 571561},
        "match_tenths": {(6, 7): 857, (4, 6): 667, (2, 32): 63},
    },
}


@pytest.mark.parametrize(
    ("matched_q", "core_q", "expected"),
    [
        pytest.param(4, 4, 301030, id="single-potato"),
        pytest.param(14, 16, 571561, id="potato-trap-curry"),
        pytest.param(6, 6, 397940, id="potato-and-peas"),
    ],
)
def test_score_int(matched_q: int, core_q: int, expected: int) -> None:
    assert score_int(matched_q, core_q) == expected


def test_potato_trap() -> None:
    """A nearly complete curry outranks a fully matched one-ingredient dish."""
    assert score_int(14, 16) > score_int(4, 4)


def test_score_int_is_an_int() -> None:
    # 571561.0 == 571561 is True, so only a type check catches a missing round().
    assert type(score_int(14, 16)) is int


@pytest.mark.parametrize(
    ("matched_q", "core_q", "expected"),
    [
        pytest.param(6, 7, 857, id="excluded-turmeric"),
        pytest.param(4, 6, 667, id="kheer-without-milk"),
        pytest.param(2, 32, 63, id="half-rounds-up"),
        pytest.param(4, 4, 1000, id="everything-matched"),
    ],
)
def test_match_tenths(matched_q: int, core_q: int, expected: int) -> None:
    assert match_tenths(matched_q, core_q) == expected


@pytest.mark.parametrize(
    "function",
    [
        pytest.param(score_int, id="score_int"),
        pytest.param(match_tenths, id="match_tenths"),
    ],
)
@pytest.mark.parametrize(
    ("matched_q", "core_q"),
    [
        pytest.param(0, 4, id="nothing-matched"),
        pytest.param(5, 4, id="more-than-core"),
        pytest.param(1, 0, id="empty-core"),
        pytest.param(-1, 4, id="negative"),
    ],
)
def test_rejects_impossible_input(
    function: Callable[[int, int], int], matched_q: int, core_q: int
) -> None:
    with pytest.raises(ValueError, match="1 <= matched_q <= core_q"):
        function(matched_q, core_q)


def test_scoring_changes_bump_the_version() -> None:
    current = {
        "weights": (MAIN, SUPPORTING, EXCLUDED_STAPLE),
        "score_int": {key: score_int(*key) for key in ((4, 4), (6, 6), (14, 16))},
        "match_tenths": {key: match_tenths(*key) for key in ((6, 7), (4, 6), (2, 32))},
    }

    assert SCORING_VERSION in SCORING_FINGERPRINTS, "add a row for the new version"
    assert current == SCORING_FINGERPRINTS[SCORING_VERSION], (
        "scoring changed: bump SCORING_VERSION and add a row; don't edit the old one"
    )


def test_score_triangle_is_indexed_the_way_postgres_reads_it() -> None:
    """ADR-0007 rule 2: 1-based index core_q * (core_q - 1) // 2 + matched_q."""
    triangle = score_triangle(16)

    assert len(triangle) == 16 * 17 // 2
    for core_q in range(1, 17):
        for matched_q in range(1, core_q + 1):
            index = core_q * (core_q - 1) // 2 + matched_q
            assert triangle[index - 1] == score_int(matched_q, core_q)
