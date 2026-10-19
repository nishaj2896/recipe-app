"""Runtime configuration from the environment (ADR-0003 rule 9 keys).

Task 4 replaces this with pydantic-settings; the variable names stay.
"""

import base64
import binascii
import json
from collections.abc import Mapping
from pathlib import Path

from recipe_app.domain.cursor import SigningKeys

KEYS_VARIABLE = "CURSOR_SIGNING_KEYS"
ACTIVE_KID_VARIABLE = "CURSOR_ACTIVE_KID"
DATA_DIR_VARIABLE = "RECIPE_APP_DATA_DIR"
DEFAULT_DATA_DIR = Path("data")
DATABASE_URL_VARIABLE = "DATABASE_URL"
DATABASE_SCHEME = "postgresql+asyncpg"


class ConfigError(ValueError):
    """The app must not start: a required setting is missing or invalid."""


def signing_keys_from_env(environ: Mapping[str, str]) -> SigningKeys:
    """Read the cursor keys: a JSON object of kid -> base64url key, and the active kid.

    Error messages name kids, never key material.
    """
    raw = environ.get(KEYS_VARIABLE)
    active = environ.get(ACTIVE_KID_VARIABLE)
    if not raw or not active:
        raise ConfigError(f"{KEYS_VARIABLE} and {ACTIVE_KID_VARIABLE} must be set")
    try:
        encoded = json.loads(raw)
    except ValueError:
        raise ConfigError(f"{KEYS_VARIABLE} is not a JSON object") from None
    if not isinstance(encoded, dict) or not all(
        isinstance(kid, str) and kid and isinstance(key, str)
        for kid, key in encoded.items()
    ):
        raise ConfigError(f"{KEYS_VARIABLE} must map key ids to base64url strings")

    keys: dict[str, bytes] = {}
    for kid, key in encoded.items():
        try:
            keys[kid] = base64.b64decode(
                key + "=" * (-len(key) % 4), altchars=b"-_", validate=True
            )
        except (binascii.Error, ValueError):
            raise ConfigError(f"key {kid!r} is not base64url") from None
    try:
        return SigningKeys(active_kid=active, keys=keys)
    except ValueError as error:
        raise ConfigError(str(error)) from None


def data_dir_from_env(environ: Mapping[str, str]) -> Path:
    """Where the data files are; defaults to ./data, the repo root's folder."""
    data_dir = Path(environ.get(DATA_DIR_VARIABLE) or DEFAULT_DATA_DIR)
    if not data_dir.is_dir():
        raise ConfigError(
            f"data directory {str(data_dir)!r} not found; set {DATA_DIR_VARIABLE}"
        )
    return data_dir


def database_url_from_env(environ: Mapping[str, str]) -> str:
    """The SQLAlchemy URL of the app's database; it must use asyncpg.

    Error messages never echo the URL, because it usually holds a password.
    """
    url = environ.get(DATABASE_URL_VARIABLE)
    if not url:
        raise ConfigError(f"{DATABASE_URL_VARIABLE} must be set")
    if not url.startswith(f"{DATABASE_SCHEME}://"):
        raise ConfigError(
            f"{DATABASE_URL_VARIABLE} must start with {DATABASE_SCHEME}://"
        )
    return url
