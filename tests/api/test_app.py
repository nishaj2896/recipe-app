import base64
import json
import logging
from collections.abc import Iterator

import pytest

from recipe_app.api.app import build_app
from recipe_app.infra.config import ConfigError
from recipe_app.infra.data import load_catalog
from tests.domain.factories import DATA_DIR

KEY = base64.urlsafe_b64encode(b"k" * 32).decode()


@pytest.fixture
def bare_app_logger() -> Iterator[logging.Logger]:
    """The `recipe_app` logger as a fresh process has it: no handler, no level."""
    app_logger = logging.getLogger("recipe_app")
    saved = app_logger.handlers[:], app_logger.level
    app_logger.handlers.clear()
    app_logger.setLevel(logging.NOTSET)
    yield app_logger
    app_logger.handlers[:], level = saved
    app_logger.setLevel(level)


def test_build_app_logs_the_catalog_hash_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    bare_app_logger: logging.Logger,
) -> None:
    """ADR-0002 rule 7: you can always tell which catalog a pod runs.

    Reads stderr, not caplog: caplog sees records that no handler would print.
    """
    monkeypatch.setenv("CURSOR_SIGNING_KEYS", json.dumps({"a": KEY}))
    monkeypatch.setenv("CURSOR_ACTIVE_KID", "a")
    monkeypatch.setenv("RECIPE_APP_DATA_DIR", str(DATA_DIR))

    build_app()

    stderr = capfd.readouterr().err
    assert load_catalog(DATA_DIR).content_hash in stderr
    assert "INFO recipe_app.api.app" in stderr


def test_build_app_refuses_to_start_without_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CURSOR_SIGNING_KEYS", raising=False)
    monkeypatch.setenv("RECIPE_APP_DATA_DIR", str(DATA_DIR))

    with pytest.raises(ConfigError):
        build_app()
