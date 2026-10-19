from typing import Any

import pytest
from pydantic import ValidationError

from recipe_app.api.schemas import SearchRequest


def errors(**body: Any) -> list[str]:
    try:
        SearchRequest.model_validate({"ingredient_ids": ["potato"]} | body)
    except ValidationError as error:
        return [".".join(map(str, e["loc"])) for e in error.errors()]
    return []


def test_defaults() -> None:
    request = SearchRequest.model_validate({"ingredient_ids": ["potato"]})

    assert request.limit == 20
    assert request.excluded_staples == []
    assert request.hidden_recipe_ids == []
    assert request.diet is None
    assert request.max_total_minutes is None
    assert request.cursor is None


@pytest.mark.parametrize(
    ("body", "field"),
    [
        pytest.param({"limit": "20"}, "limit", id="limit-string"),
        pytest.param({"limit": True}, "limit", id="limit-bool"),
        pytest.param({"limit": 20.5}, "limit", id="limit-float"),
        pytest.param({"max_total_minutes": "30"}, "max_total_minutes", id="time-str"),
        pytest.param({"ingredient_ids": ["Potato"]}, "ingredient_ids.0", id="caps"),
        pytest.param({"ingredient_ids": ["potato "]}, "ingredient_ids.0", id="space"),
        pytest.param({"ingredient_ids": ["a--b"]}, "ingredient_ids.0", id="slug"),
        pytest.param(
            {"excluded_staples": ["salt", "salt"]}, "excluded_staples", id="dup-staple"
        ),
        pytest.param(
            {
                "hidden_recipe_ids": [
                    "019a0c3e-8f00-7a1b-9c2d-3e4f5a6b7c8d",
                    "019a0c3e-8f00-7a1b-9c2d-3e4f5a6b7c8d",
                ]
            },
            "hidden_recipe_ids",
            id="dup-hidden",
        ),
        pytest.param({"cursor": ""}, "cursor", id="empty-cursor"),
        pytest.param({"diet": "jain"}, "diet", id="unknown-diet"),
    ],
)
def test_rejected(body: dict[str, Any], field: str) -> None:
    assert field in errors(**body)


def test_request_is_immutable() -> None:
    request = SearchRequest.model_validate({"ingredient_ids": ["potato"]})

    with pytest.raises(ValidationError):
        request.limit = 5  # type: ignore[misc]
