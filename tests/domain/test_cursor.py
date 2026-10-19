"""The signed cursor (ADR-0003 rule 9)."""

import base64
import json
from uuid import UUID

import pytest

from recipe_app.domain.catalog import Diet
from recipe_app.domain.cursor import (
    MAX_AGE_SECONDS,
    MAX_CLOCK_SKEW_SECONDS,
    MAX_CURSOR_LENGTH,
    ExpiredCursorError,
    InvalidCursorError,
    Position,
    Scope,
    SigningKeys,
    decode_cursor,
    encode_cursor,
    request_fingerprint,
)

NOW = 1_800_000_000
KEY_A = b"a" * 32
KEY_B = b"b" * 32
KEYS = SigningKeys(active_kid="a", keys={"a": KEY_A})


def fingerprint(
    *,
    diet: Diet | None = Diet.VEGETARIAN,
    max_total_minutes: int | None = 30,
    ingredient_ids: tuple[str, ...] = ("potato", "peas"),
    excluded_staples: tuple[str, ...] = ("turmeric",),
) -> str:
    return request_fingerprint(
        diet=diet,
        max_total_minutes=max_total_minutes,
        ingredient_ids=ingredient_ids,
        excluded_staples=excluded_staples,
    )


REQ = fingerprint()
SCOPE = Scope(catalog="c" * 64, scoring=1, req=REQ)
POSITION = Position(
    scored=(-571561, 40, UUID(int=7)),
    all_staples=(15, UUID(int=1001)),
)


def issue(
    position: Position = POSITION,
    scope: Scope = SCOPE,
    keys: SigningKeys = KEYS,
    now: int = NOW,
) -> str:
    return encode_cursor(position, scope, keys, now=now)


def read(
    token: str,
    scope: Scope = SCOPE,
    keys: SigningKeys = KEYS,
    now: int = NOW,
) -> Position:
    return decode_cursor(token, scope, keys, now=now)


# Round trip


@pytest.mark.parametrize(
    "position",
    [
        pytest.param(POSITION, id="both-tiers"),
        pytest.param(Position(scored=(-301030, 20, UUID(int=3))), id="scored-only"),
        pytest.param(Position(all_staples=(10, UUID(int=1002))), id="staples-only"),
        pytest.param(Position(), id="empty"),
    ],
)
def test_round_trip(position: Position) -> None:
    assert read(issue(position)) == position


def test_cursor_is_url_safe_without_padding() -> None:
    token = issue()

    assert "=" not in token
    assert set(token) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_."
    )


def test_same_inputs_give_the_same_cursor() -> None:
    assert issue() == issue()


# The request fingerprint


def test_fingerprint_ignores_list_order() -> None:
    assert fingerprint(ingredient_ids=("peas", "potato")) == REQ


def test_omitted_diet_fingerprints_as_non_veg() -> None:
    """7b.3: both return every recipe (ADR-0002 rule 6)."""
    assert fingerprint(diet=None) == fingerprint(diet=Diet.NON_VEG)


@pytest.mark.parametrize(
    "changed",
    [
        pytest.param(fingerprint(diet=Diet.VEGAN), id="diet"),
        pytest.param(fingerprint(max_total_minutes=31), id="max-time"),
        pytest.param(fingerprint(max_total_minutes=None), id="max-time-omitted"),
        pytest.param(fingerprint(ingredient_ids=("potato",)), id="ingredients"),
        pytest.param(fingerprint(excluded_staples=()), id="excluded-staples"),
    ],
)
def test_fingerprint_changes_with_each_filter(changed: str) -> None:
    assert changed != REQ


# Invalid: a client bug or tampering


def test_tampered_payload_is_invalid() -> None:
    payload, signature = issue().split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["pos"]["scored"][0] = -999999
    forged = (
        base64.urlsafe_b64encode(
            json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
        )
        .rstrip(b"=")
        .decode()
    )

    with pytest.raises(InvalidCursorError, match="signature"):
        read(f"{forged}.{signature}")


def test_cursor_reused_with_other_filters_is_invalid() -> None:
    other = Scope(catalog=SCOPE.catalog, scoring=1, req="0" * 64)

    with pytest.raises(InvalidCursorError, match="filters"):
        read(issue(), scope=other)


def test_too_long_is_rejected_before_decoding() -> None:
    """1,025 characters of junk: if it were decoded first, the error would differ."""
    with pytest.raises(InvalidCursorError, match="too long"):
        read("!" * (MAX_CURSOR_LENGTH + 1))


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="empty"),
        pytest.param("no-dot-here", id="no-signature"),
        pytest.param("!!!.!!!", id="not-base64"),
        pytest.param(".", id="empty-parts"),
    ],
)
def test_malformed_is_invalid(token: str) -> None:
    with pytest.raises(InvalidCursorError):
        read(token)


@pytest.mark.parametrize("char", ["*", "+", "/", "="])
def test_characters_outside_base64url_are_rejected_not_dropped(char: str) -> None:
    """A lenient decoder drops `*` or reads `+` as `-`, then reports a bad signature."""
    payload, signature = issue(Position()).split(".")
    with pytest.raises(InvalidCursorError, match="not base64url"):
        read(f"{payload[:5]}{char}{payload[5:]}.{signature}")


# Expired: normal, the app restarts at page 1


def test_older_than_24_hours_is_expired() -> None:
    token = issue(now=NOW - MAX_AGE_SECONDS - 1)

    with pytest.raises(ExpiredCursorError, match="24 hours"):
        read(token)


def test_exactly_24_hours_old_still_works() -> None:
    assert read(issue(now=NOW - MAX_AGE_SECONDS)) == POSITION


def test_small_clock_skew_is_allowed() -> None:
    assert read(issue(now=NOW + MAX_CLOCK_SKEW_SECONDS)) == POSITION


def test_far_future_is_expired() -> None:
    with pytest.raises(ExpiredCursorError, match="future"):
        read(issue(now=NOW + MAX_CLOCK_SKEW_SECONDS + 1))


def test_other_catalog_is_expired() -> None:
    with pytest.raises(ExpiredCursorError, match="catalog"):
        read(issue(), scope=Scope(catalog="d" * 64, scoring=1, req=REQ))


def test_other_scoring_version_is_expired() -> None:
    with pytest.raises(ExpiredCursorError, match="scoring"):
        read(issue(), scope=Scope(catalog=SCOPE.catalog, scoring=2, req=REQ))


# Key rotation


def test_rotation_old_key_still_verifies_after_new_key_is_active() -> None:
    token = issue(keys=SigningKeys(active_kid="a", keys={"a": KEY_A}))
    rotated = SigningKeys(active_kid="b", keys={"a": KEY_A, "b": KEY_B})

    assert read(token, keys=rotated) == POSITION


def test_rotation_removed_key_is_expired() -> None:
    token = issue(keys=SigningKeys(active_kid="a", keys={"a": KEY_A}))
    removed = SigningKeys(active_kid="b", keys={"b": KEY_B})

    with pytest.raises(ExpiredCursorError, match="key"):
        read(token, keys=removed)


def test_same_kid_with_another_key_is_invalid() -> None:
    other = SigningKeys(active_kid="a", keys={"a": KEY_B})

    with pytest.raises(InvalidCursorError, match="signature"):
        read(issue(), keys=other)


# Keys


def test_short_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        SigningKeys(active_kid="a", keys={"a": b"x" * 31})


def test_active_key_must_be_listed() -> None:
    with pytest.raises(ValueError, match="active key"):
        SigningKeys(active_kid="b", keys={"a": KEY_A})
