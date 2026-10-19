import base64
import json
import logging

import pytest

from recipe_app.api.app import build_app
from recipe_app.infra.config import ConfigError
from recipe_app.infra.data import load_catalog
from tests.domain.factories import DATA_DIR

KEY = base64.urlsafe_b64encode(b"k" * 32).decode()


def test_build_app_logs_the_catalog_hash(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """ADR-0002 rule 7: you can always tell which catalog a pod runs."""
    monkeypatch.setenv("CURSOR_SIGNING_KEYS", json.dumps({"a": KEY}))
    monkeypatch.setenv("CURSOR_ACTIVE_KID", "a")
    monkeypatch.setenv("RECIPE_APP_DATA_DIR", str(DATA_DIR))

    with caplog.at_level(logging.INFO, logger="recipe_app"):
        build_app()

    assert load_catalog(DATA_DIR).content_hash in caplog.text


def test_build_app_refuses_to_start_without_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CURSOR_SIGNING_KEYS", raising=False)
    monkeypatch.setenv("RECIPE_APP_DATA_DIR", str(DATA_DIR))

    with pytest.raises(ConfigError):
        build_app()
