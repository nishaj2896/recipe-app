from dataclasses import replace
from uuid import UUID

from recipe_app.api.presenters import _scored_card, recipe_detail
from recipe_app.domain.catalog import parse_catalog
from recipe_app.domain.content import Amount, RecipeContent, RecipeWithContent
from recipe_app.domain.matching import ScoredMatch
from recipe_app.domain.recipe import Image, build_recipe
from recipe_app.domain.units import Unit
from tests.domain.factories import catalog, category, ingredient

CATALOG = parse_catalog(catalog(category(), ingredient()))
RECIPE = build_recipe(
    id=UUID(int=3),
    name="Boiled potatoes",
    prep_minutes=5,
    cook_minutes=20,
    ingredient_ids=["potato"],
    catalog=CATALOG,
)


def test_photo_url_is_versioned_by_its_hash() -> None:
    """ADR-0008 rule 6: a regenerated photo is a new URL, so caches can keep it."""
    content = RecipeContent(
        serves=2,
        amounts=(Amount(value=4, unit=Unit.MEDIUM),),
        steps=("Boil the potatoes.", "Serve."),
        image=Image(
            file=f"{RECIPE.id}.webp", sha256="0123456789ab" + "f" * 52, alt="x"
        ),
    )

    detail = recipe_detail(RecipeWithContent(recipe=RECIPE, content=content))

    assert detail.image is not None
    assert detail.image.url == f"/dishes/{RECIPE.id}.webp?v=0123456789ab"
    assert detail.serves == 2
    assert (detail.ingredients[0].amount, detail.ingredients[0].unit) == (
        4,
        Unit.MEDIUM,
    )


def test_the_card_carries_the_photo_with_the_same_versioned_url() -> None:
    """ADR-0010: the swipe card shows the photo, so the card has its URL."""
    photo = Image(file=f"{RECIPE.id}.webp", sha256="0123456789ab" + "f" * 52, alt="x")
    match = ScoredMatch(
        recipe=replace(RECIPE, image=photo),
        score_int=1,
        match_tenths=1000,
        matched=RECIPE.ingredients,
        missing=(),
        assumed=(),
    )
    plain = ScoredMatch(
        recipe=RECIPE,
        score_int=1,
        match_tenths=1000,
        matched=RECIPE.ingredients,
        missing=(),
        assumed=(),
    )

    card, bare = _scored_card(match), _scored_card(plain)

    assert card.image is not None
    assert card.image.url == f"/dishes/{RECIPE.id}.webp?v=0123456789ab"
    assert card.image.alt == "x"
    assert bare.image is None


def test_a_recipe_without_content_still_lists_its_ingredients() -> None:
    detail = recipe_detail(RecipeWithContent(recipe=RECIPE, content=None))

    assert detail.serves is None
    assert detail.steps == []
    assert detail.image is None
    assert [(i.id, i.amount, i.unit) for i in detail.ingredients] == [
        ("potato", None, None)
    ]


def test_the_plan_ahead_wait_is_on_the_detail() -> None:
    waits = build_recipe(
        id=UUID(int=4),
        name="Soaked potatoes",
        prep_minutes=5,
        cook_minutes=20,
        ingredient_ids=["potato"],
        catalog=CATALOG,
        plan_ahead={"wait_minutes": 480, "note": "soak overnight"},
    )

    detail = recipe_detail(RecipeWithContent(recipe=waits, content=None))
    plain = recipe_detail(RecipeWithContent(recipe=RECIPE, content=None))

    assert detail.plan_ahead is not None
    assert (detail.plan_ahead.wait_minutes, detail.plan_ahead.note) == (
        480,
        "soak overnight",
    )
    assert plain.plan_ahead is None
