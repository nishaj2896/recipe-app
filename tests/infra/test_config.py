"""Settings from the environment (ADR-0013 rule 8, ADR-0005 rule 7)."""

import base64
import json
from pathlib import Path

import pytest

from recipe_app.infra.config import (
    ApiSettings,
    ConfigError,
    DatabaseSettings,
    SyncSettings,
)

KEY = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")
PASSWORD = "p%40ssw0rd-hunter2"  # noqa: S105 (a test value, never a real one)
URL = f"postgresql+asyncpg://recipe_app:{PASSWORD}@localhost:5432/recipe_app"
VARIABLES = (
    "DATABASE_URL",
    "CURSOR_SIGNING_KEYS",
    "CURSOR_ACTIVE_KID",
    "API_DOCS",
    "RECIPE_APP_DATA_DIR",
    "LOG_LEVEL",
    "LOG_FORMAT",
)


@pytest.fixture
def environ(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A clean slate for every variable the settings read."""
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def set_api(
    environ: pytest.MonkeyPatch, keys: object = None, active: str = "a"
) -> None:
    environ.setenv("DATABASE_URL", URL)
    raw = keys if isinstance(keys, str) else json.dumps(keys or {"a": KEY})
    environ.setenv("CURSOR_SIGNING_KEYS", raw)
    environ.setenv("CURSOR_ACTIVE_KID", active)


# DATABASE_URL


def test_database_url_loads(environ: pytest.MonkeyPatch) -> None:
    environ.setenv("DATABASE_URL", URL)

    assert DatabaseSettings.from_env().url == URL


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        pytest.param(None, "DATABASE_URL must be set", id="unset"),
        pytest.param("", "DATABASE_URL must be set", id="empty"),
        pytest.param(
            "postgresql://u:hunter2@localhost/db",
            r"DATABASE_URL must start with postgresql\+asyncpg://",
            id="sync-driver",
        ),
    ],
)
def test_bad_database_url_refuses_to_start(
    environ: pytest.MonkeyPatch, value: str | None, expected: str
) -> None:
    if value is not None:
        environ.setenv("DATABASE_URL", value)

    with pytest.raises(ConfigError, match=expected) as caught:
        DatabaseSettings.from_env()

    assert "hunter2" not in str(caught.value)


def test_the_url_is_secret_when_printed(environ: pytest.MonkeyPatch) -> None:
    environ.setenv("DATABASE_URL", URL)

    settings = DatabaseSettings.from_env()

    assert PASSWORD not in repr(settings)
    assert PASSWORD not in str(settings)


def test_the_summary_hides_the_password(environ: pytest.MonkeyPatch) -> None:
    environ.setenv("DATABASE_URL", URL)

    summary = DatabaseSettings.from_env().summary()

    assert summary == {
        "DATABASE_URL": "postgresql+asyncpg://recipe_app:***@localhost:5432/recipe_app"
    }


@pytest.mark.parametrize(
    "query",
    ["?password=s3cret", "?sslpassword=s3cret&ssl=require", "?options=-c%20x%3Ds3cret"],
)
def test_the_summary_drops_the_query(environ: pytest.MonkeyPatch, query: str) -> None:
    """A password can sit in the query, not only before the @ (review of #127)."""
    environ.setenv("DATABASE_URL", f"postgresql+asyncpg://u@db:5432/app{query}")

    summary = DatabaseSettings.from_env().summary()

    assert summary == {"DATABASE_URL": "postgresql+asyncpg://u@db:5432/app?***"}
    assert "s3cret" not in str(summary)


def test_names_are_exact(environ: pytest.MonkeyPatch) -> None:
    """Only DATABASE_URL counts; a lower-case look-alike is not read."""
    environ.setenv("database_url", URL)

    with pytest.raises(ConfigError, match="DATABASE_URL must be set"):
        DatabaseSettings.from_env()


# The cursor keys and API_DOCS


def test_keys_load(environ: pytest.MonkeyPatch) -> None:
    set_api(environ, {"a": KEY, "b": KEY}, active="b")

    keys = ApiSettings.from_env().signing_keys

    assert keys.active_kid == "b"
    assert keys.keys == {"a": b"k" * 32, "b": b"k" * 32}


@pytest.mark.parametrize(
    ("keys", "active", "expected"),
    [
        pytest.param("{nope", "a", "not a JSON object", id="not-json"),
        pytest.param(["a"], "a", "must map key ids", id="not-object"),
        pytest.param({"a": 1}, "a", "must map key ids", id="not-string"),
        pytest.param(
            {"a": "!!!"},
            "a",
            "^CURSOR_SIGNING_KEYS: key 'a' is not base64url$",
            id="not-base64",
        ),
        pytest.param(
            {"a": KEY}, "b", "^CURSOR_ACTIVE_KID: .*not in keys", id="active-missing"
        ),
        pytest.param(
            {"a": "c2hvcnQ"}, "a", "^CURSOR_SIGNING_KEYS: .*shorter than 32", id="short"
        ),
    ],
)
def test_bad_keys_refuse_to_start(
    environ: pytest.MonkeyPatch, keys: object, active: str, expected: str
) -> None:
    set_api(environ, keys, active)

    with pytest.raises(ConfigError, match=expected) as caught:
        ApiSettings.from_env()

    assert KEY not in str(caught.value)


def test_unset_keys_name_both_variables(environ: pytest.MonkeyPatch) -> None:
    environ.setenv("DATABASE_URL", URL)

    with pytest.raises(ConfigError) as caught:
        ApiSettings.from_env()

    assert str(caught.value) == (
        "CURSOR_SIGNING_KEYS must be set; CURSOR_ACTIVE_KID must be set"
    )


def test_every_problem_is_reported_at_once(environ: pytest.MonkeyPatch) -> None:
    """One restart shows every mistake, not one per restart."""
    environ.setenv("API_DOCS", "yes")

    with pytest.raises(ConfigError) as caught:
        ApiSettings.from_env()

    message = str(caught.value)
    for part in ("DATABASE_URL", "CURSOR_SIGNING_KEYS", "API_DOCS"):
        assert part in message


def test_the_keys_are_secret_when_printed(environ: pytest.MonkeyPatch) -> None:
    set_api(environ)

    settings = ApiSettings.from_env()

    assert KEY not in repr(settings)
    assert KEY not in str(settings.summary())


def test_the_api_summary_names_kids_not_keys(environ: pytest.MonkeyPatch) -> None:
    set_api(environ, {"b": KEY, "a": KEY}, active="b")

    summary = ApiSettings.from_env().summary()

    assert summary["CURSOR_SIGNING_KEYS"] == "2 keys (a, b)"
    assert summary["CURSOR_ACTIVE_KID"] == "b"
    assert summary["API_DOCS"] == "false"
    assert summary["LOG_LEVEL"] == "INFO"
    assert summary["LOG_FORMAT"] == "json"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, False), ("", False), ("false", False), ("true", True), (" TRUE ", True)],
)
def test_docs_flag(
    environ: pytest.MonkeyPatch, value: str | None, expected: bool
) -> None:
    set_api(environ)
    if value is not None:
        environ.setenv("API_DOCS", value)

    assert ApiSettings.from_env().api_docs is expected


@pytest.mark.parametrize("value", ["1", "yes", "on", "ture"])
def test_bad_docs_flag_refuses_to_start(
    environ: pytest.MonkeyPatch, value: str
) -> None:
    set_api(environ)
    environ.setenv("API_DOCS", value)

    with pytest.raises(ConfigError, match=r"^API_DOCS must be true or false$"):
        ApiSettings.from_env()


# RECIPE_APP_DATA_DIR


def test_sync_needs_no_cursor_keys(environ: pytest.MonkeyPatch) -> None:
    environ.setenv("DATABASE_URL", URL)

    assert SyncSettings.from_env().data_dir == Path("data")


def test_data_dir_from_env(environ: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environ.setenv("DATABASE_URL", URL)
    environ.setenv("RECIPE_APP_DATA_DIR", str(tmp_path))

    assert SyncSettings.from_env().data_dir == tmp_path


def test_empty_data_dir_is_the_default(environ: pytest.MonkeyPatch) -> None:
    environ.setenv("DATABASE_URL", URL)
    environ.setenv("RECIPE_APP_DATA_DIR", "")

    assert SyncSettings.from_env().data_dir == Path("data")


def test_missing_data_dir_refuses_to_start(
    environ: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environ.setenv("DATABASE_URL", URL)
    environ.setenv("RECIPE_APP_DATA_DIR", str(tmp_path / "nope"))

    with pytest.raises(ConfigError, match="RECIPE_APP_DATA_DIR"):
        SyncSettings.from_env()


# LOG_LEVEL and LOG_FORMAT


def test_log_defaults_are_info_and_json(environ: pytest.MonkeyPatch) -> None:
    set_api(environ)

    settings = ApiSettings.from_env()

    assert (settings.log_level, settings.log_format) == ("INFO", "json")


@pytest.mark.parametrize(
    ("level", "fmt", "expected"),
    [
        ("debug", " TEXT ", ("DEBUG", "text")),
        ("", "", ("INFO", "json")),
        ("Warning", "json", ("WARNING", "json")),
    ],
)
def test_log_settings_ignore_case_and_spaces(
    environ: pytest.MonkeyPatch, level: str, fmt: str, expected: tuple[str, str]
) -> None:
    set_api(environ)
    environ.setenv("LOG_LEVEL", level)
    environ.setenv("LOG_FORMAT", fmt)

    settings = ApiSettings.from_env()

    assert (settings.log_level, settings.log_format) == expected


@pytest.mark.parametrize(
    ("name", "value"), [("LOG_LEVEL", "verbose"), ("LOG_FORMAT", "xml")]
)
def test_bad_log_settings_refuse_to_start(
    environ: pytest.MonkeyPatch, name: str, value: str
) -> None:
    set_api(environ)
    environ.setenv(name, value)

    with pytest.raises(ConfigError, match=f"^{name}: ") as caught:
        ApiSettings.from_env()

    assert value not in str(caught.value)
