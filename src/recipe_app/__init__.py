def main() -> None:
    """Run the API locally: `uv run recipe-app` (see README for the keys)."""
    import uvicorn

    uvicorn.run("recipe_app.api.app:build_app", factory=True)
