"""The Task 1 verification gate, one test per checkbox, through HTTP only.

Where an ADR changed a gate check, the test follows the ADR and its
docstring says which one. Static checks (ruff, mypy) run in CI.
"""

import ast
import base64
import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response

from recipe_app.api.problems import (
    CURSOR_EXPIRED,
    INVALID_CURSOR,
    PROBLEM_MEDIA_TYPE,
)
from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.domain.recipe import Recipe
from recipe_app.domain.scoring import SCORING_VERSION
from recipe_app.services import search as search_service
from recipe_app.services.ports import RecipeRepository
from tests.apps import NOW, AppFactory, client_for
from tests.contract.conftest import (
    CHANA,
    CHICKEN_CURRY,
    EGG_CURRY,
    GHEE_DAL,
    KHEER,
    OKRA_FRY,
    PANEER_PEAS,
    PEANUT_EGG_SALAD,
    POTATO_CURRY,
    QUICK_PEAS_RICE,
    SLOW_PEAS_RICE,
    SLOW_POTATO,
    TOMATO_SOUP,
    bulk,
)

pytestmark = pytest.mark.anyio

SEARCH = "/api/v1/recipes/search"
SRC = Path(__file__).parents[2] / "src" / "recipe_app"
MAX_PAGES = 100


async def search(client: AsyncClient, **body: Any) -> Response:
    return await client.post(SEARCH, json=body)


def cards(response: Response) -> list[dict[str, Any]]:
    assert response.status_code == 200, response.text
    results: list[dict[str, Any]] = response.json()["results"]
    return results


def card(response: Response, recipe_id: UUID) -> dict[str, Any]:
    return next(c for c in cards(response) if c["id"] == str(recipe_id))


def ids(items: list[dict[str, Any]]) -> list[str]:
    return [item["id"] for item in items]


def assert_problem(response: Response, status: int, problem_type: str) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    body = response.json()
    assert body["type"] == problem_type
    assert body["status"] == status
    assert "Traceback" not in response.text


async def walk(client: AsyncClient, **body: Any) -> list[dict[str, Any]]:
    """Every deck, following next_cursor until it is null."""
    decks: list[dict[str, Any]] = []
    cursor = None
    for _ in range(MAX_PAGES):
        response = await search(client, **body, cursor=cursor)
        assert response.status_code == 200, response.text
        decks.append(response.json())
        cursor = decks[-1]["next_cursor"]
        if cursor is None:
            return decks
    raise AssertionError(f"next_cursor still set after {MAX_PAGES} decks")


# Static checks


@pytest.mark.parametrize("layer", ["domain", "services"])
def test_inner_layers_import_no_framework(layer: str) -> None:
    """`grep -r fastapi src/recipe_app/domain` returns nothing, as an AST check."""
    banned = {"fastapi", "starlette", "pydantic", "httpx", "uvicorn"}
    for path in (SRC / layer).rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert name.split(".")[0] not in banned, f"{path} imports {name}"


# Contract checks


async def openapi(client: AsyncClient) -> dict[str, Any]:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema: dict[str, Any] = response.json()
    return schema


async def test_every_endpoint_documents_success_and_error_models(
    gate: AsyncClient,
) -> None:
    schema = await openapi(gate)

    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            responses = operation["responses"]
            ok = responses["200"]["content"]["application/json"]["schema"]
            assert "$ref" in ok, f"{method} {path} has no success model"
            errors = {code: r for code, r in responses.items() if code[0] in "45"}
            assert "500" in errors, f"{method} {path} documents no 500"
            for code, response in errors.items():
                problem = response["content"][PROBLEM_MEDIA_TYPE]["schema"]
                assert problem == {"$ref": "#/components/schemas/Problem"}, (
                    f"{method} {path} {code}"
                )


async def test_pantry_bounds_are_in_the_schema(gate: AsyncClient) -> None:
    request = (await openapi(gate))["components"]["schemas"]["SearchRequest"]
    pantry = request["properties"]["ingredient_ids"]

    assert (pantry["minItems"], pantry["maxItems"]) == (1, 50)
    assert pantry["uniqueItems"] is True
    assert pantry["items"]["maxLength"] == 64
    assert pantry["items"]["minLength"] == 1
    assert request["properties"]["hidden_recipe_ids"]["maxItems"] == 200
    assert request["properties"]["excluded_staples"]["maxItems"] == 100


async def test_request_schemas_forbid_extra_properties(gate: AsyncClient) -> None:
    schemas = (await openapi(gate))["components"]["schemas"]

    assert schemas["SearchRequest"]["additionalProperties"] is False


# Behavioral tests


async def test_happy_path_is_ranked_with_correct_missing_lists(
    gate: AsyncClient,
) -> None:
    response = await search(gate, ingredient_ids=["potato", "peas"])
    scored = [c for c in cards(response) if c["tier"] == "scored"]

    assert ids(scored)[0] == str(POTATO_CURRY)
    percentages = [c["match_percentage"] for c in scored]
    assert percentages[0] == 100.0
    dum_aloo = card(response, SLOW_POTATO)
    assert dum_aloo["missing_ingredients"] == [{"id": "curd", "name": "Curd"}]
    assert dum_aloo["matched_ingredients"] == [{"id": "potato", "name": "Potato"}]


async def test_ids_not_text_never_published_id_is_rejected(gate: AsyncClient) -> None:
    """ADR-0001 replaced the free-text normalization check with id checks."""
    response = await search(gate, ingredient_ids=["potato", "tomatoes"])

    assert_problem(response, 422, "about:blank")
    assert response.json()["errors"] == [
        {"field": "ingredient_ids", "message": "unknown ingredient 'tomatoes'"}
    ]


@pytest.mark.parametrize(
    "pantry",
    [
        pytest.param(["Tomato"], id="capitals"),
        pytest.param([" tomato "], id="spaces"),
        pytest.param(["potato", "potato"], id="duplicate"),
    ],
)
async def test_ids_are_exact_slugs_and_unique(
    gate: AsyncClient, pantry: list[str]
) -> None:
    """ADR-0001 rule 3: no normalization on the request path, duplicates are 422."""
    assert_problem(await search(gate, ingredient_ids=pantry), 422, "about:blank")


async def test_empty_pantry_is_422(gate: AsyncClient) -> None:
    response = await search(gate, ingredient_ids=[])

    assert_problem(response, 422, "about:blank")
    assert response.json()["errors"][0]["field"] == "ingredient_ids"


async def test_pantry_over_the_limit_is_422(gate: AsyncClient) -> None:
    pantry = [f"item-{n}" for n in range(51)]

    assert_problem(await search(gate, ingredient_ids=pantry), 422, "about:blank")


async def test_ingredient_id_over_max_length_is_rejected(gate: AsyncClient) -> None:
    response = await search(gate, ingredient_ids=["a" * 65])

    assert_problem(response, 422, "about:blank")
    assert response.json()["errors"][0]["field"] == "ingredient_ids[0]"


async def test_unknown_field_is_rejected(gate: AsyncClient) -> None:
    response = await search(gate, ingredient_ids=["potato"], ingredients=["potato"])

    assert_problem(response, 422, "about:blank")
    assert response.json()["errors"] == [
        {"field": "ingredients", "message": "Extra inputs are not permitted"}
    ]


async def test_wrong_type_is_rejected_with_the_envelope(gate: AsyncClient) -> None:
    response = await search(gate, ingredient_ids="egg")

    assert_problem(response, 422, "about:blank")
    assert response.json()["title"] == "Invalid request"


async def test_unknown_recipe_is_404(gate: AsyncClient) -> None:
    missing = uuid4()
    response = await gate.get(f"/api/v1/recipes/{missing}")

    assert_problem(response, 404, "about:blank")
    assert response.json()["detail"] == f"No recipe exists with id {missing}."


@pytest.mark.parametrize("bad", ["123", "not-a-uuid", "1" * 40])
async def test_malformed_recipe_id_is_422_not_500(gate: AsyncClient, bad: str) -> None:
    assert_problem(await gate.get(f"/api/v1/recipes/{bad}"), 422, "about:blank")


async def test_same_request_twice_is_byte_identical(gate: AsyncClient) -> None:
    body = {"ingredient_ids": ["potato", "peas", "rice"], "excluded_staples": ["salt"]}

    first = await gate.post(SEARCH, json=body)
    second = await gate.post(SEARCH, json=body)

    assert first.content == second.content


async def test_staples_are_assumed(gate: AsyncClient) -> None:
    response = await search(gate, ingredient_ids=["potato", "peas"])
    curry = card(response, POTATO_CURRY)

    assert curry["match_percentage"] == 100.0
    assert curry["missing_ingredients"] == []
    assert ids(curry["assumed_staples"]) == [
        "tomato",
        "onion",
        "turmeric",
        "salt",
        "ghee",
    ]


async def test_all_staples_recipe_comes_after_every_scored_card(
    gate: AsyncClient,
) -> None:
    results = cards(await search(gate, ingredient_ids=["potato", "peas", "egg"]))
    tiers = [c["tier"] for c in results]
    soup = next(c for c in results if c["id"] == str(TOMATO_SOUP))

    assert tiers == sorted(tiers, key=lambda tier: tier == "all_staples")
    assert soup["tier"] == "all_staples"
    assert soup["match_percentage"] is None


async def test_unchecked_staple_scores_and_is_missing(gate: AsyncClient) -> None:
    """ADR-0003: weighted, so 1.5 of 1.75 is 85.7%, not the plain 6 of 7."""
    response = await search(
        gate, ingredient_ids=["potato", "peas"], excluded_staples=["turmeric"]
    )
    curry = card(response, POTATO_CURRY)

    assert curry["match_percentage"] == 85.7
    assert curry["missing_ingredients"] == [{"id": "turmeric", "name": "Turmeric"}]
    assert "turmeric" not in ids(curry["assumed_staples"])


async def test_never_published_excluded_staple_is_422(gate: AsyncClient) -> None:
    response = await search(
        gate, ingredient_ids=["potato"], excluded_staples=["saffron-x"]
    )

    assert_problem(response, 422, "about:blank")
    assert response.json()["errors"][0]["field"] == "excluded_staples"


async def test_excluded_non_staple_is_ignored_not_rejected(gate: AsyncClient) -> None:
    """ADR-0002 rule 5 changed this check: a cached catalog must not break searches."""
    response = await search(
        gate, ingredient_ids=["potato"], excluded_staples=["paneer"]
    )

    assert response.json()["ignored_ingredients"] == [
        {"id": "paneer", "name": "Paneer", "reason": "not_staple"}
    ]


async def test_typed_pantry_staple_changes_no_card(gate: AsyncClient) -> None:
    """Same cards; the staple is reported in ignored_ingredients (ADR-0001 rule 3)."""
    with_salt = await search(gate, ingredient_ids=["potato", "peas", "salt"])
    without = await search(gate, ingredient_ids=["potato", "peas"])

    assert with_salt.json()["results"] == without.json()["results"]
    assert with_salt.json()["ignored_ingredients"] == [
        {"id": "salt", "name": "Salt", "reason": "now_staple"}
    ]


async def test_typed_fresh_staple_does_not_promote_tomato_soup(
    gate: AsyncClient,
) -> None:
    """ADR-0003 retired "typed tomato moves it out of the all-staples tier"."""
    soup = card(await search(gate, ingredient_ids=["potato", "tomato"]), TOMATO_SOUP)

    assert soup["tier"] == "all_staples"
    assert soup["match_percentage"] is None


async def test_deck_size_is_20_with_a_cursor_and_limit_21_is_422(
    make_app: AppFactory, real_catalog: IngredientCatalog
) -> None:
    """20 is 18 scored + 2 all-staples; with no all-staples recipes a deck holds
    18, because the scored cap holds either way (ADR-0003 rule 7)."""
    async with client_for(make_app(recipes=bulk(real_catalog, 30, 2))) as client:
        response = await search(client, ingredient_ids=["potato"])
        too_big = await search(client, ingredient_ids=["potato"], limit=21)

    assert len(cards(response)) == 20
    assert response.json()["next_cursor"]
    assert_problem(too_big, 422, "about:blank")


async def test_scored_cap_holds_without_all_staples_recipes(
    make_app: AppFactory, real_catalog: IngredientCatalog
) -> None:
    async with client_for(make_app(recipes=bulk(real_catalog, 40, 0))) as client:
        decks = await walk(client, ingredient_ids=["potato"])

    assert [len(d["results"]) for d in decks] == [18, 18, 4]


async def test_generate_more_returns_every_recipe_once(
    make_app: AppFactory, real_catalog: IngredientCatalog
) -> None:
    async with client_for(make_app(recipes=bulk(real_catalog, 45, 7))) as client:
        decks = await walk(client, ingredient_ids=["potato", "peas"])

    shown = [c["id"] for deck in decks for c in deck["results"]]
    assert len(shown) == len(set(shown)) == 52
    for deck in decks:
        tiers = [c["tier"] for c in deck["results"]]
        if "scored" in tiers:
            assert tiers.count("all_staples") <= 2
            assert tiers == sorted(tiers, key=lambda tier: tier == "all_staples")
    assert [len(d["results"]) for d in decks] == [20, 20, 11, 1]


async def test_pagination_has_no_gaps_with_small_decks(
    make_app: AppFactory, real_catalog: IngredientCatalog
) -> None:
    pool = bulk(real_catalog, 13, 5)
    async with client_for(make_app(recipes=pool)) as client:
        decks = await walk(client, ingredient_ids=["potato"], limit=3)

    shown = sorted(c["id"] for deck in decks for c in deck["results"])
    assert shown == sorted(str(recipe.id) for recipe in pool)


def tampered(cursor: str) -> str:
    payload, signature = cursor.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    claims["pos"]["scored"][0] -= 1
    edited = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
    return f"{base64.urlsafe_b64encode(edited).rstrip(b'=').decode()}.{signature}"


@pytest.mark.parametrize(
    "make_bad",
    [
        pytest.param(lambda _: "not-a-cursor", id="random"),
        pytest.param(lambda c: c[:-2] + ("AA" if c[-2:] != "AA" else "BB"), id="sig"),
        pytest.param(tampered, id="edited-payload"),
        pytest.param(lambda _: "x" * 1025, id="too-long"),
    ],
)
async def test_tampered_cursor_is_invalid_not_500(
    make_app: AppFactory, real_catalog: IngredientCatalog, make_bad: Any
) -> None:
    async with client_for(make_app(recipes=bulk(real_catalog, 30, 0))) as client:
        cursor = (await search(client, ingredient_ids=["potato"])).json()["next_cursor"]
        response = await search(
            client, ingredient_ids=["potato"], cursor=make_bad(cursor)
        )

    assert_problem(response, 422, INVALID_CURSOR)


async def test_milk_is_core(gate: AsyncClient) -> None:
    """ADR-0003: weighted, so rice (1.0) of rice and milk (1.5) is 66.7%."""
    kheer = card(await search(gate, ingredient_ids=["rice"]), KHEER)

    assert kheer["match_percentage"] == 66.7
    assert kheer["missing_ingredients"] == [{"id": "milk", "name": "Milk"}]
    assert ids(kheer["assumed_staples"]) == ["sugar"]


async def test_all_staples_cap_is_18_plus_2(
    make_app: AppFactory, real_catalog: IngredientCatalog
) -> None:
    async with client_for(make_app(recipes=bulk(real_catalog, 30, 10))) as client:
        decks = await walk(client, ingredient_ids=["potato"])

    tiers = [[c["tier"] for c in deck["results"]] for deck in decks]
    assert tiers[0] == ["scored"] * 18 + ["all_staples"] * 2
    assert tiers[1] == ["scored"] * 12 + ["all_staples"] * 2
    assert tiers[2] == ["all_staples"] * 6


async def test_tie_break_is_shorter_total_time(gate: AsyncClient) -> None:
    response = await search(gate, ingredient_ids=["peas", "rice"])
    quick, slow = card(response, QUICK_PEAS_RICE), card(response, SLOW_PEAS_RICE)
    order = ids(cards(response))

    assert quick["match_percentage"] == slow["match_percentage"]
    assert len(quick["missing_ingredients"]) == len(slow["missing_ingredients"])
    assert quick["total_minutes"] < slow["total_minutes"]
    assert order.index(str(QUICK_PEAS_RICE)) < order.index(str(SLOW_PEAS_RICE))


ANIMAL = {"paneer", "milk", "curd", "ghee", "butter", "egg", "chicken"}


async def test_vegan_never_returns_dairy_even_assumed(
    gate: AsyncClient, gate_recipes: tuple[Recipe, ...]
) -> None:
    by_id = {str(r.id): r for r in gate_recipes}
    decks = await walk(
        gate,
        ingredient_ids=["potato", "peas", "rice", "toor-dal", "okra"],
        diet="vegan",
    )
    shown = [c["id"] for deck in decks for c in deck["results"]]

    assert str(OKRA_FRY) in shown
    for recipe_id in shown:
        used = {item.id for item in by_id[recipe_id].ingredients}
        assert not used & ANIMAL, by_id[recipe_id].name
    assert str(POTATO_CURRY) not in shown  # assumed ghee
    assert str(GHEE_DAL) not in shown


async def test_diet_hierarchy(gate: AsyncClient) -> None:
    pantry = ["potato", "peas", "paneer", "egg", "chicken", "chickpeas"]

    async def shown(diet: str | None) -> set[str]:
        body: dict[str, Any] = {"ingredient_ids": pantry}
        if diet:
            body["diet"] = diet
        decks = await walk(gate, **body)
        return {c["id"] for deck in decks for c in deck["results"]}

    vegan, vegetarian, egg, non_veg, omitted = [
        await shown(d) for d in ("vegan", "vegetarian", "egg", "non_veg", None)
    ]
    assert str(CHANA) in vegan
    assert vegan < vegetarian < egg < non_veg == omitted
    assert str(PANEER_PEAS) in vegetarian
    assert str(CHICKEN_CURRY) in non_veg - egg


async def test_egg_is_its_own_level(gate: AsyncClient) -> None:
    """ADR-0002 rule 6 replaced "egg is non-veg" with an egg diet level."""
    for diet, expected in [("vegan", False), ("vegetarian", False), ("egg", True)]:
        response = await search(gate, ingredient_ids=["egg"], diet=diet)
        assert (str(EGG_CURRY) in ids(cards(response))) is expected, diet


async def test_time_filter(gate: AsyncClient) -> None:
    response = await search(gate, ingredient_ids=["potato"], max_total_minutes=30)

    assert str(SLOW_POTATO) not in ids(cards(response))  # 10 prep + 25 cook
    assert str(POTATO_CURRY) in ids(cards(response))  # 10 + 20
    for bad in (0, 100_000):
        too = await search(gate, ingredient_ids=["potato"], max_total_minutes=bad)
        assert_problem(too, 422, "about:blank")


async def test_hidden_recipes_never_appear(
    make_app: AppFactory, real_catalog: IngredientCatalog
) -> None:
    pool = bulk(real_catalog, 30, 4)
    hidden = [str(pool[0].id), str(pool[25].id), str(pool[-1].id)]
    async with client_for(make_app(recipes=pool)) as client:
        decks = await walk(client, ingredient_ids=["potato"], hidden_recipe_ids=hidden)
        too_many = await search(
            client,
            ingredient_ids=["potato"],
            hidden_recipe_ids=[str(uuid4()) for _ in range(201)],
        )
        malformed = await search(
            client, ingredient_ids=["potato"], hidden_recipe_ids=["not-a-uuid"]
        )

    shown = {c["id"] for deck in decks for c in deck["results"]}
    assert len(decks) == 2
    assert not shown & set(hidden)
    assert len(shown) == len(pool) - 3
    assert_problem(too_many, 422, "about:blank")
    assert_problem(malformed, 422, "about:blank")


async def test_hiding_between_decks_keeps_the_cursor_valid(
    make_app: AppFactory, real_catalog: IngredientCatalog
) -> None:
    pool = bulk(real_catalog, 40, 0)
    async with client_for(make_app(recipes=pool)) as client:
        first = (await search(client, ingredient_ids=["potato"])).json()
        hide = [first["results"][0]["id"]]
        second = await search(
            client,
            ingredient_ids=["potato"],
            hidden_recipe_ids=hide,
            cursor=first["next_cursor"],
        )

    assert not set(ids(cards(second))) & set(ids(first["results"]))


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"diet": "vegan"}, id="diet"),
        pytest.param({"max_total_minutes": 30}, id="time"),
        pytest.param({"ingredient_ids": ["potato", "rice"]}, id="pantry"),
        pytest.param({"excluded_staples": ["salt"]}, id="excluded"),
    ],
)
async def test_cursor_with_other_filters_is_invalid(
    make_app: AppFactory, real_catalog: IngredientCatalog, change: dict[str, Any]
) -> None:
    body: dict[str, Any] = {"ingredient_ids": ["potato"]}
    async with client_for(make_app(recipes=bulk(real_catalog, 30, 0))) as client:
        cursor = (await search(client, **body)).json()["next_cursor"]
        response = await search(client, **(body | change), cursor=cursor)

    assert_problem(response, 422, INVALID_CURSOR)


async def test_omitted_diet_and_non_veg_share_a_cursor(
    make_app: AppFactory, real_catalog: IngredientCatalog
) -> None:
    async with client_for(make_app(recipes=bulk(real_catalog, 30, 0))) as client:
        cursor = (await search(client, ingredient_ids=["potato"])).json()["next_cursor"]
        response = await search(
            client, ingredient_ids=["potato"], diet="non_veg", cursor=cursor
        )

    assert response.status_code == 200


async def test_old_cursor_is_expired(
    make_app: AppFactory, real_catalog: IngredientCatalog
) -> None:
    pool = bulk(real_catalog, 30, 0)
    async with client_for(make_app(recipes=pool)) as client:
        cursor = (await search(client, ingredient_ids=["potato"])).json()["next_cursor"]
    async with client_for(make_app(recipes=pool, now=NOW + 86_401)) as later:
        response = await search(later, ingredient_ids=["potato"], cursor=cursor)

    assert_problem(response, 422, CURSOR_EXPIRED)


async def test_cursor_from_another_catalog_is_expired(
    make_app: AppFactory, real_catalog: IngredientCatalog
) -> None:
    """ADR-0003 rule 9: a catalog change restarts the deck, it is not an error."""
    pool = bulk(real_catalog, 30, 0)
    async with client_for(make_app(recipes=pool)) as client:
        cursor = (await search(client, ingredient_ids=["potato"])).json()["next_cursor"]
    changed = replace(real_catalog, content_hash="0" * 64)
    async with client_for(make_app(recipes=pool, catalog=changed)) as later:
        response = await search(later, ingredient_ids=["potato"], cursor=cursor)

    assert_problem(response, 422, CURSOR_EXPIRED)


async def test_cursor_from_another_scoring_version_is_expired(
    make_app: AppFactory,
    real_catalog: IngredientCatalog,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = bulk(real_catalog, 30, 0)
    async with client_for(make_app(recipes=pool)) as client:
        cursor = (await search(client, ingredient_ids=["potato"])).json()["next_cursor"]
    monkeypatch.setattr(search_service, "SCORING_VERSION", SCORING_VERSION + 1)
    async with client_for(make_app(recipes=pool)) as later:
        response = await search(later, ingredient_ids=["potato"], cursor=cursor)

    assert_problem(response, 422, CURSOR_EXPIRED)


async def test_regional_names_live_in_search_terms(gate: AsyncClient) -> None:
    """ADR-0001 retired the aloo/bhindi alias check; synonyms are search terms."""
    body = (await gate.get("/api/v1/ingredients")).json()
    okra = next(i for i in body["ingredients"] if i["id"] == "okra")

    assert "lady finger" in okra["search_terms"]
    assert not any(i["id"] in {"aloo", "bhindi", "jeera"} for i in body["ingredients"])


async def test_staples_endpoint_is_complete_grouped_and_stable(
    gate: AsyncClient, real_catalog: IngredientCatalog
) -> None:
    first = await gate.get("/api/v1/staples")
    second = await gate.get("/api/v1/staples")
    groups = first.json()["groups"]

    assert first.content == second.content
    assert [g["kind"] for g in groups] == ["fresh", "pantry"]
    shown = [s["id"] for g in groups for cat in g["categories"] for s in cat["staples"]]
    expected = [
        i.id
        for i in real_catalog.by_id.values()
        if i.ingredient_class == "S" and not i.retired
    ]
    assert sorted(shown) == sorted(expected)
    assert len(shown) == len(set(shown))


async def test_cumin_seeds_and_powder_are_separate_staples(gate: AsyncClient) -> None:
    """ADR-0001 rule 5 replaced the cumin/jeera alias check with two ids."""
    groups = (await gate.get("/api/v1/staples")).json()["groups"]
    pantry = next(g for g in groups if g["kind"] == "pantry")
    names = {s["id"] for cat in pantry["categories"] for s in cat["staples"]}

    assert {"cumin-seeds", "cumin-powder"} <= names


async def test_staples_never_swallow_similar_ingredients(gate: AsyncClient) -> None:
    """The oil and salt staples don't hide egg or peanuts: ids, not substrings."""
    salad = card(await search(gate, ingredient_ids=["peanuts"]), PEANUT_EGG_SALAD)

    assert salad["missing_ingredients"] == [{"id": "egg", "name": "Egg"}]
    assert ids(salad["assumed_staples"]) == ["oil", "salt"]


async def test_only_staples_typed_shows_only_all_staples_cards(
    gate: AsyncClient,
) -> None:
    """Q11 and Q13: never divides by zero, and staple ids are ignored, not errors."""
    response = await search(gate, ingredient_ids=["tomato", "salt"])

    assert {c["tier"] for c in cards(response)} == {"all_staples"}
    assert all(c["match_percentage"] is None for c in cards(response))
    assert ids(response.json()["ignored_ingredients"]) == ["tomato", "salt"]


async def test_zero_matches_is_200_and_empty(gate: AsyncClient) -> None:
    response = await search(gate, ingredient_ids=["mango"], excluded_staples=["tomato"])

    # Unticking tomato puts the only all-staples recipe, tomato soup, in play
    # as a scored recipe with nothing matched, so nothing at all is left.
    assert response.json() == {
        "results": [],
        "next_cursor": None,
        "ignored_ingredients": [],
    }


class BrokenRepository:
    async def get(self, recipe_id: UUID) -> Recipe | None:
        raise RuntimeError("db password is hunter2")

    async def candidates(self, *_: object) -> list[Recipe]:
        raise RuntimeError("db password is hunter2")


async def test_forced_internal_error_is_a_generic_500(
    real_catalog: IngredientCatalog,
) -> None:
    from recipe_app.api.app import create_app
    from recipe_app.services.search import RecipeService
    from tests.apps import KEYS

    repository: RecipeRepository = BrokenRepository()
    service = RecipeService(
        catalog=real_catalog, repository=repository, keys=KEYS, clock=lambda: NOW
    )
    async with client_for(create_app(catalog=real_catalog, service=service)) as client:
        searched = await search(client, ingredient_ids=["potato"])
        fetched = await client.get(f"/api/v1/recipes/{uuid4()}")

    for response in (searched, fetched):
        assert_problem(response, 500, "about:blank")
        assert "hunter2" not in response.text
        assert "RuntimeError" not in response.text


async def test_docs_render(gate: AsyncClient) -> None:
    response = await gate.get("/docs")

    assert response.status_code == 200
    assert "swagger-ui" in response.text
