import json
from typing import Any

import pytest
import uvicorn

from recipe_app.cli import main
from recipe_app.domain.recipe import Recipe
from tests.domain.factories import DATA_DIR

KEYS = json.dumps({"a": "a" * 43})


def test_db_sync_loads_the_data_files(
    migrated_database_url: str,
    seed: tuple[Recipe, ...],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_database_url)
    monkeypatch.setenv("RECIPE_APP_DATA_DIR", str(DATA_DIR))

    assert main(["db", "sync"]) == 0
    assert f"{len(seed)} recipes" in capsys.readouterr().out


def test_db_sync_without_a_database_url_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main(["db", "sync"]) == 1
    assert "DATABASE_URL must be set" in capsys.readouterr().err


def test_openapi_prints_the_document_the_web_app_is_built_from(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No settings or database needed: CI runs it to check web/'s types."""
    assert main(["openapi"]) == 0

    document = json.loads(capsys.readouterr().out)
    assert "/api/v1/recipes/search" in document["paths"]
    assert "RecipeCard" in document["components"]["schemas"]


@pytest.mark.usefixtures("bare_app_logger")
def test_serve_runs_uvicorn_with_the_limits_from_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-0013 rule 7: one worker, our logging, the drain and keep-alive."""
    seen: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(app=app, **kw))
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db/app")
    monkeypatch.setenv("CURSOR_SIGNING_KEYS", KEYS)
    monkeypatch.setenv("CURSOR_ACTIVE_KID", "a")
    monkeypatch.setenv("SHUTDOWN_GRACE_SECONDS", "12")
    monkeypatch.setenv("API_PORT", "9001")

    assert main(["serve"]) == 0
    assert seen == {
        "app": "recipe_app.api.app:build_app",
        "factory": True,
        "host": "127.0.0.1",
        "port": 9001,
        "workers": 1,
        "log_config": None,
        "access_log": False,
        "timeout_graceful_shutdown": 12,
        "timeout_keep_alive": 75,
    }


def test_serve_without_settings_exits_1_before_listening(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(uvicorn, "run", pytest.fail)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main([]) == 1
    assert "DATABASE_URL must be set" in capsys.readouterr().err
