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
    assert request.min_total_minutes is None
    assert request.jain is False
    assert request.avoid_allergens == []
    assert request.avoid_ingredient_ids == []
    assert request.courses == []
    assert request.moods == []
    assert request.weather == []


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
        pytest.param({"jain": True}, "jain", id="jain-without-diet"),
        pytest.param({"jain": True, "diet": "egg"}, "jain", id="jain-with-egg"),
        pytest.param({"jain": "true"}, "jain", id="jain-string"),
        pytest.param(
            {"min_total_minutes": 31, "max_total_minutes": 30},
            "min_total_minutes",
            id="min-above-max",
        ),
        pytest.param({"min_total_minutes": 0}, "min_total_minutes", id="min-zero"),
        pytest.param(
            {"avoid_allergens": ["nuts"]}, "avoid_allergens.0", id="unknown-allergen"
        ),
        pytest.param(
            {"avoid_allergens": ["egg", "egg"]}, "avoid_allergens", id="dup-allergen"
        ),
        pytest.param(
            {"avoid_ingredient_ids": ["Coconut"]},
            "avoid_ingredient_ids.0",
            id="avoid-caps",
        ),
        pytest.param({"courses": ["lunch"]}, "courses.0", id="unknown-course"),
        pytest.param({"moods": ["spicy", "spicy"]}, "moods", id="dup-mood"),
        pytest.param({"weather": ["sunny"]}, "weather.0", id="unknown-weather"),
    ],
)
def test_rejected(body: dict[str, Any], field: str) -> None:
    assert field in errors(**body)


@pytest.mark.parametrize("diet", ["vegetarian", "vegan"])
def test_jain_with_a_vegetarian_diet_is_accepted(diet: str) -> None:
    assert errors(jain=True, diet=diet) == []


def test_min_equal_to_max_is_accepted() -> None:
    assert errors(min_total_minutes=30, max_total_minutes=30) == []


def test_every_mood_screen_pick_at_once_is_accepted() -> None:
    assert (
        errors(
            courses=["mains", "sides"],
            moods=["spicy", "tangy", "creamy"],
            weather=["rainy-day-cosy"],
            avoid_allergens=["peanuts", "tree-nuts"],
            avoid_ingredient_ids=["coconut"],
            min_total_minutes=61,
        )
        == []
    )


def test_request_is_immutable() -> None:
    request = SearchRequest.model_validate({"ingredient_ids": ["potato"]})

    with pytest.raises(ValidationError):
        request.limit = 5  # type: ignore[misc]
