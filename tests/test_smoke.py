import recipe_app


def test_smoke() -> None:
    """The package imports and pytest is wired up."""
    assert recipe_app is not None
