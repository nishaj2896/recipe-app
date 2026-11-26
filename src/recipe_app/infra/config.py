"""Runtime configuration from the environment (ADR-0013 rule 8).

Each command reads only the settings it needs: the API, `recipe-app db sync`
and the migrations share DATABASE_URL, and only the API needs the cursor keys.
A missing or invalid value raises ConfigError before anything starts
(ADR-0005 rule 7). Messages name the variable, never its value, and secrets are
SecretStr, so printing a settings object shows `**********`.
"""

import base64
import binascii
import json
from pathlib import Path
from typing import Any, Self

from pydantic import (
    Field,
    PrivateAttr,
    SecretStr,
    ValidationError,
    ValidationInfo,
    field_validator,
)
from pydantic import model_validator as model_check
from pydantic_core import ErrorDetails
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from recipe_app.domain.cursor import SigningKeys
from recipe_app.infra.logs import LogFormat, LogLevel

KEYS_VARIABLE = "CURSOR_SIGNING_KEYS"
ACTIVE_KID_VARIABLE = "CURSOR_ACTIVE_KID"
DATA_DIR_VARIABLE = "RECIPE_APP_DATA_DIR"
DEFAULT_DATA_DIR = Path("data")
DATABASE_URL_VARIABLE = "DATABASE_URL"
DATABASE_SCHEME = "postgresql+asyncpg"
DOCS_VARIABLE = "API_DOCS"


class ConfigError(ValueError):
    """The app must not start: a required setting is missing or invalid."""


class _Settings(BaseSettings):
    # Aliases are literal strings: the pydantic mypy plugin checks them. Exact
    # variable names only, no .env file (scripts/dev.sh sources it), and
    # never the rejected value in an error, should one reach a log.
    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    @classmethod
    def from_env(cls) -> Self:
        """Read os.environ; any problem is one ConfigError naming every variable."""
        try:
            return cls()
        except ValidationError as error:
            raise ConfigError(
                "; ".join(_describe(e) for e in error.errors(include_input=False))
            ) from None


class DatabaseSettings(_Settings):
    """What every command needs: where the database is."""

    database_url: SecretStr = Field(validation_alias="DATABASE_URL")

    @field_validator("database_url", mode="before")
    @classmethod
    def _check_url(cls, value: Any) -> Any:
        # The message never echoes the URL: it usually holds a password.
        if not isinstance(value, str) or not value:
            raise ValueError(f"{DATABASE_URL_VARIABLE} must be set")
        if not value.startswith(f"{DATABASE_SCHEME}://"):
            raise ValueError(
                f"{DATABASE_URL_VARIABLE} must start with {DATABASE_SCHEME}://"
            )
        return value

    @property
    def url(self) -> str:
        return self.database_url.get_secret_value()

    def summary(self) -> dict[str, str]:
        """The settings as a startup log line shows them, secrets hidden."""
        return {DATABASE_URL_VARIABLE: _redacted(self.url)}


class ApiSettings(DatabaseSettings):
    """What the API server reads."""

    cursor_signing_keys: SecretStr = Field(validation_alias="CURSOR_SIGNING_KEYS")
    cursor_active_kid: str = Field(validation_alias="CURSOR_ACTIVE_KID", min_length=1)
    api_docs: bool = Field(False, validation_alias="API_DOCS")
    log_level: LogLevel = Field("INFO", validation_alias="LOG_LEVEL")
    log_format: LogFormat = Field("json", validation_alias="LOG_FORMAT")
    _keys: SigningKeys = PrivateAttr()

    @field_validator("api_docs", mode="before")
    @classmethod
    def _check_docs(cls, value: Any) -> bool:
        """Off unless set to true: the schema maps every route and error.

        Anything but true or false is a typo, and the app refuses to start
        rather than guess, so pydantic's yes/on/1 are refused too.
        """
        raw = (value if isinstance(value, str) else str(value)).strip().lower()
        if raw not in ("", "true", "false"):
            raise ValueError(f"{DOCS_VARIABLE} must be true or false")
        return raw == "true"

    @field_validator("log_level", "log_format", mode="before")
    @classmethod
    def _normalise_choice(cls, value: Any, info: ValidationInfo) -> Any:
        """Unset or empty is the default; case and spaces don't matter."""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return "INFO" if info.field_name == "log_level" else "json"
        return text.upper() if info.field_name == "log_level" else text.lower()

    @model_check(mode="after")
    def _parse_keys(self) -> Self:
        self._keys = _signing_keys(
            self.cursor_signing_keys.get_secret_value(), self.cursor_active_kid
        )
        return self

    @property
    def signing_keys(self) -> SigningKeys:
        return self._keys

    def summary(self) -> dict[str, str]:
        kids = ", ".join(sorted(self._keys.keys))
        return {
            **super().summary(),
            ACTIVE_KID_VARIABLE: self.cursor_active_kid,
            KEYS_VARIABLE: f"{_count(len(self._keys.keys), 'key')} ({kids})",
            DOCS_VARIABLE: str(self.api_docs).lower(),
            "LOG_LEVEL": self.log_level,
            "LOG_FORMAT": self.log_format,
        }


class SyncSettings(DatabaseSettings):
    """What `recipe-app db sync` reads."""

    data_dir: Path = Field(DEFAULT_DATA_DIR, validation_alias="RECIPE_APP_DATA_DIR")

    @field_validator("data_dir", mode="before")
    @classmethod
    def _default_when_empty(cls, value: Any) -> Any:
        return value or DEFAULT_DATA_DIR

    @field_validator("data_dir", mode="after")
    @classmethod
    def _check_dir(cls, value: Path) -> Path:
        if not value.is_dir():
            raise ValueError(
                f"data directory {str(value)!r} not found; set {DATA_DIR_VARIABLE}"
            )
        return value


def _signing_keys(raw: str, active: str) -> SigningKeys:
    """A JSON object of kid -> base64url key. Errors name kids, never keys."""
    try:
        encoded = json.loads(raw)
    except ValueError:
        raise ValueError(f"{KEYS_VARIABLE} is not a JSON object") from None
    if not isinstance(encoded, dict) or not all(
        isinstance(kid, str) and kid and isinstance(key, str)
        for kid, key in encoded.items()
    ):
        raise ValueError(f"{KEYS_VARIABLE} must map key ids to base64url strings")

    keys: dict[str, bytes] = {}
    for kid, key in encoded.items():
        try:
            keys[kid] = base64.b64decode(
                key + "=" * (-len(key) % 4), altchars=b"-_", validate=True
            )
        except (binascii.Error, ValueError):
            raise ValueError(f"{KEYS_VARIABLE}: key {kid!r} is not base64url") from None
    try:
        return SigningKeys(active_kid=active, keys=keys)
    except ValueError as error:
        # The domain names kids, never key material; say which variable to fix.
        variable = ACTIVE_KID_VARIABLE if active not in keys else KEYS_VARIABLE
        raise ValueError(f"{variable}: {error}") from None


def _describe(error: ErrorDetails) -> str:
    """One readable sentence per error, from the variable name and our message.

    Pydantic's own messages never quote the input here (include_input=False,
    hide_input_in_errors), and ours never hold a value either.
    """
    variable = str(error["loc"][0]) if error["loc"] else ""
    if error["type"] == "missing":
        return f"{variable} must be set"
    message = error["msg"].removeprefix("Value error, ")
    if not variable or message.startswith(variable):
        return message
    return f"{variable}: {message}"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _redacted(url: str) -> str:
    """Scheme, user, host, port and database only.

    The query is dropped whole, not filtered: libpq-style options such as
    `?password=...` or `?sslpassword=...` carry secrets, and a list of names
    to hide would miss the next one.
    """
    try:
        parsed = make_url(url)
    except ArgumentError:
        return "(unparseable)"
    shown = parsed.set(query={}).render_as_string(hide_password=True)
    return f"{shown}?***" if parsed.query else shown
