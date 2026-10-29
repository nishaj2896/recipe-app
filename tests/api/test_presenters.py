from uuid import UUID

from recipe_app.api.presenters import recipe_detail
from recipe_app.domain.catalog import parse_catalog
from recipe_app.domain.content import Amount, Image, RecipeContent, RecipeWithContent
from recipe_app.domain.recipe import build_recipe
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


def test_a_recipe_without_content_still_lists_its_ingredients() -> None:
    detail = recipe_detail(RecipeWithContent(recipe=RECIPE, content=None))

    assert detail.serves is None
    assert detail.steps == []
    assert detail.image is None
    assert [(i.id, i.amount, i.unit) for i in detail.ingredients] == [
        ("potato", None, None)
    ]
