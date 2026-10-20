def main() -> None:
    """`uv run recipe-app` serves the API; `uv run recipe-app db sync` loads data."""
    from recipe_app.cli import main as run

    raise SystemExit(run())
