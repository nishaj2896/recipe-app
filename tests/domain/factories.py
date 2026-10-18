"""Small inline catalogs for tests: one valid row each, override a field to break it."""

import json
from pathlib import Path

DATA_FILE = Path(__file__).parents[2] / "data" / "ingredients.v1.toml"


def category(**fields: object) -> str:
    """A valid [[category]] table for vegetables. Override fields; None drops one."""
    row: dict[str, object] = {
        "id": "vegetables",
        "name": "Vegetables",
        "position": 10,
    } | fields
    lines = [
        f"{key} = {json.dumps(value)}"
        for key, value in row.items()
        if value is not None
    ]
    return "[[category]]\n" + "\n".join(lines) + "\n"


def ingredient(**fields: object) -> str:
    """A valid [[ingredient]] table for potato. Override fields; None drops one."""
    row: dict[str, object] = {
        "id": "potato",
        "name": "Potato",
        "class": "A",
        "diet": "vegan",
        "category": "vegetables",
    } | fields
    lines = [
        f"{key} = {json.dumps(value)}"
        for key, value in row.items()
        if value is not None
    ]
    return "[[ingredient]]\n" + "\n".join(lines) + "\n"


def catalog(*tables: str) -> bytes:
    return "\n".join(tables).encode()
