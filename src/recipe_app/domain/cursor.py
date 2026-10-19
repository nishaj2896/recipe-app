"""The signed "generate more" cursor (ADR-0003 rule 9).

Pure: the clock and the signing keys are passed in, never read here.
"""

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from uuid import UUID

from recipe_app.domain.catalog import Diet

CURSOR_VERSION = 1
MAX_CURSOR_LENGTH = 1024
MAX_AGE_SECONDS = 24 * 60 * 60
MAX_CLOCK_SKEW_SECONDS = 5 * 60
MIN_KEY_BYTES = 32
BASE64URL = re.compile(r"[A-Za-z0-9_-]*")

type ScoredKey = tuple[int, int, UUID]
type AllStaplesKey = tuple[int, UUID]


class CursorError(ValueError):
    """A cursor the server won't resume from."""


class InvalidCursorError(CursorError):
    """Malformed, tampered or used with other filters: a client bug or an attack."""


class ExpiredCursorError(CursorError):
    """Too old, or issued under another catalog, scoring or key: restart quietly."""


@dataclass(frozen=True, slots=True)
class SigningKeys:
    """Every key verifies; only the active one signs."""

    active_kid: str
    keys: Mapping[str, bytes]

    def __post_init__(self) -> None:
        if self.active_kid not in self.keys:
            raise ValueError(f"active key {self.active_kid!r} is not in keys")
        short = sorted(
            kid for kid, key in self.keys.items() if len(key) < MIN_KEY_BYTES
        )
        if short:
            raise ValueError(f"keys shorter than {MIN_KEY_BYTES} bytes: {short}")


@dataclass(frozen=True, slots=True)
class Scope:
    """What a cursor is only valid for: this catalog, scoring and request."""

    catalog: str
    scoring: int
    req: str


@dataclass(frozen=True, slots=True)
class Position:
    """The sort key of the last card shown in each tier; None if none yet."""

    scored: ScoredKey | None = None
    all_staples: AllStaplesKey | None = None


def request_fingerprint(
    *,
    diet: Diet | None,
    max_total_minutes: int | None,
    ingredient_ids: Iterable[str],
    excluded_staples: Iterable[str],
) -> str:
    """SHA-256 of the filters that change the list; `hidden_recipe_ids` is left out."""
    canonical = _canonical(
        {
            "diet": str(diet or Diet.NON_VEG),
            "max_total_minutes": max_total_minutes,
            "ingredient_ids": sorted(ingredient_ids),
            "excluded_staples": sorted(excluded_staples),
        }
    )
    return hashlib.sha256(canonical).hexdigest()


def encode_cursor(
    position: Position, scope: Scope, keys: SigningKeys, *, now: int
) -> str:
    payload = _canonical(
        {
            "v": CURSOR_VERSION,
            "kid": keys.active_kid,
            "iat": now,
            "catalog": scope.catalog,
            "scoring": scope.scoring,
            "req": scope.req,
            "pos": _position_to_json(position),
        }
    )
    signature = _sign(keys.keys[keys.active_kid], payload)
    return f"{_b64encode(payload)}.{_b64encode(signature)}"


def decode_cursor(token: str, scope: Scope, keys: SigningKeys, *, now: int) -> Position:
    """Check everything ADR-0003 rule 9 lists, cheapest first."""
    if len(token) > MAX_CURSOR_LENGTH:
        raise InvalidCursorError("too long")
    payload_part, dot, signature_part = token.partition(".")
    if not dot:
        raise InvalidCursorError("no signature")
    payload = _b64decode(payload_part)
    signature = _b64decode(signature_part)
    claims = _json_object(payload)

    kid = claims.get("kid")
    if not isinstance(kid, str):
        raise InvalidCursorError("no key id")
    if kid not in keys.keys:
        raise ExpiredCursorError("signed with a key we no longer accept")
    if not hmac.compare_digest(_sign(keys.keys[kid], payload), signature):
        raise InvalidCursorError("bad signature")

    if claims.get("v") != CURSOR_VERSION:
        raise ExpiredCursorError("unsupported cursor version")
    iat = claims.get("iat")
    if not isinstance(iat, int):
        raise InvalidCursorError("no issued-at time")
    if now - iat > MAX_AGE_SECONDS:
        raise ExpiredCursorError("older than 24 hours")
    if iat - now > MAX_CLOCK_SKEW_SECONDS:
        raise ExpiredCursorError("issued in the future")
    if claims.get("req") != scope.req:
        raise InvalidCursorError("issued for other filters")
    if claims.get("catalog") != scope.catalog:
        raise ExpiredCursorError("issued for another catalog")
    if claims.get("scoring") != scope.scoring:
        raise ExpiredCursorError("issued under another scoring version")
    return _position_from_json(claims.get("pos"))


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sign(key: bytes, payload: bytes) -> bytes:
    return hmac.new(key, payload, hashlib.sha256).digest()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64decode(text: str) -> bytes:
    # altchars maps "-_" onto "+/" before validating, so "+" and "/" need this.
    if not BASE64URL.fullmatch(text):
        raise InvalidCursorError("not base64url")
    try:
        return base64.b64decode(
            text + "=" * (-len(text) % 4), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError) as error:
        raise InvalidCursorError("not base64url") from error


def _json_object(payload: bytes) -> dict[str, object]:
    try:
        claims = json.loads(payload)
    except ValueError as error:
        raise InvalidCursorError("not JSON") from error
    if not isinstance(claims, dict):
        raise InvalidCursorError("not a JSON object")
    return claims


def _position_to_json(position: Position) -> dict[str, object]:
    scored = all_staples = None
    if position.scored is not None:
        neg_score, minutes, recipe_id = position.scored
        scored = [neg_score, minutes, str(recipe_id)]
    if position.all_staples is not None:
        minutes, recipe_id = position.all_staples
        all_staples = [minutes, str(recipe_id)]
    return {"scored": scored, "all_staples": all_staples}


def _position_from_json(raw: object) -> Position:
    """Only a bug in this module can get here with a bad shape: it was signed."""
    if not isinstance(raw, dict):
        raise InvalidCursorError("no position")
    try:
        scored = raw["scored"]
        all_staples = raw["all_staples"]
        return Position(
            scored=None
            if scored is None
            else (_int(scored[0]), _int(scored[1]), UUID(scored[2])),
            all_staples=None
            if all_staples is None
            else (_int(all_staples[0]), UUID(all_staples[1])),
        )
    except (AttributeError, KeyError, IndexError, TypeError, ValueError) as error:
        raise InvalidCursorError("bad position") from error


def _int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"not an int: {value!r}")
    return value
