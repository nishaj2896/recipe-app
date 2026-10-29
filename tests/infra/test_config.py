import base64
import json
from pathlib import Path

import pytest

from recipe_app.infra.config import (
    ConfigError,
    data_dir_from_env,
    docs_enabled_from_env,
    signing_keys_from_env,
)

KEY = base64.urlsafe_b64encode(b"k" * 32).decode().rstrip("=")


def env(keys: object, active: str = "a") -> dict[str, str]:
    raw = keys if isinstance(keys, str) else json.dumps(keys)
    return {"CURSOR_SIGNING_KEYS": raw, "CURSOR_ACTIVE_KID": active}


def test_keys_load() -> None:
    keys = signing_keys_from_env(env({"a": KEY, "b": KEY}, active="b"))

    assert keys.active_kid == "b"
    assert keys.keys == {"a": b"k" * 32, "b": b"k" * 32}


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        pytest.param({}, "must be set", id="unset"),
        pytest.param(env("{nope"), "not a JSON object", id="not-json"),
        pytest.param(env(["a"]), "must map key ids", id="not-object"),
        pytest.param(env({"a": 1}), "must map key ids", id="not-string"),
        pytest.param(env({"a": "!!!"}), "not base64url", id="not-base64"),
        pytest.param(env({"a": KEY}, active="b"), "not in keys", id="active-missing"),
        pytest.param(env({"a": "c2hvcnQ"}), "shorter than 32", id="short"),
    ],
)
def test_bad_keys_refuse_to_start(environ: dict[str, str], expected: str) -> None:
    with pytest.raises(ConfigError, match=expected) as caught:
        signing_keys_from_env(environ)

    assert KEY not in str(caught.value)


def test_data_dir_defaults_to_data() -> None:
    assert data_dir_from_env({}) == Path("data")


def test_data_dir_from_env(tmp_path: Path) -> None:
    assert data_dir_from_env({"RECIPE_APP_DATA_DIR": str(tmp_path)}) == tmp_path


def test_missing_data_dir_refuses_to_start(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="RECIPE_APP_DATA_DIR"):
        data_dir_from_env({"RECIPE_APP_DATA_DIR": str(tmp_path / "nope")})


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, False),
        ({"API_DOCS": ""}, False),
        ({"API_DOCS": "false"}, False),
        ({"API_DOCS": "true"}, True),
        ({"API_DOCS": " TRUE "}, True),
    ],
)
def test_docs_flag(environ: dict[str, str], expected: bool) -> None:
    assert docs_enabled_from_env(environ) is expected


@pytest.mark.parametrize("value", ["1", "yes", "on", "ture"])
def test_bad_docs_flag_refuses_to_start(value: str) -> None:
    with pytest.raises(ConfigError, match="API_DOCS must be true or false"):
        docs_enabled_from_env({"API_DOCS": value})
