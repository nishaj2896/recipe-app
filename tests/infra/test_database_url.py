import pytest

from recipe_app.infra.config import ConfigError, database_url_from_env

URL = "postgresql+asyncpg://recipe_app:p%40ss@localhost:5432/recipe_app"


def test_database_url_loads() -> None:
    assert database_url_from_env({"DATABASE_URL": URL}) == URL


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        pytest.param({}, "must be set", id="unset"),
        pytest.param({"DATABASE_URL": ""}, "must be set", id="empty"),
        pytest.param(
            {"DATABASE_URL": "postgresql://u:p@localhost/db"},
            "must start with postgresql",
            id="sync-driver",
        ),
    ],
)
def test_bad_database_url_refuses_to_start(
    environ: dict[str, str], expected: str
) -> None:
    with pytest.raises(ConfigError, match=expected):
        database_url_from_env(environ)


def test_error_never_shows_the_password() -> None:
    with pytest.raises(ConfigError) as error:
        database_url_from_env({"DATABASE_URL": "postgres://u:hunter2@db/app"})

    assert "hunter2" not in str(error.value)
