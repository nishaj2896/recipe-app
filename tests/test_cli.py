import json

import pytest

from recipe_app.cli import main
from recipe_app.domain.recipe import Recipe
from tests.domain.factories import DATA_DIR


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
