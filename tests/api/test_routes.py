import pytest
from httpx import AsyncClient

from recipe_app.api.problems import PROBLEM_MEDIA_TYPE
from tests.apps import AppFactory, client_for

pytestmark = pytest.mark.anyio

SEARCH = "/api/v1/recipes/search"


async def test_search_card_shape(client: AsyncClient) -> None:
    response = await client.post(SEARCH, json={"ingredient_ids": ["potato", "peas"]})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"results", "next_cursor", "ignored_ingredients"}
    first = body["results"][0]
    assert first["name"] == "Aloo matar"
    assert first["tier"] == "scored"
    assert first["match_percentage"] == 100.0
    assert first["matched_ingredients"] == [
        {"id": "potato", "name": "Potato"},
        {"id": "peas", "name": "Peas"},
    ]
    assert first["missing_ingredients"] == []
    assert first["total_minutes"] == first["prep_minutes"] + first["cook_minutes"]
    assert first["diet"] == "vegetarian"
    assert first["plan_ahead"] is None
    assert first["image"] is None


async def test_all_staples_card_has_no_percentage(client: AsyncClient) -> None:
    response = await client.post(SEARCH, json={"ingredient_ids": ["kingfish"]})

    staples = [c for c in response.json()["results"] if c["tier"] == "all_staples"]
    assert staples
    assert all(card["match_percentage"] is None for card in staples)
    assert all(card["matched_ingredients"] == [] for card in staples)
    assert all(card["missing_ingredients"] == [] for card in staples)


async def test_ignored_ingredients_are_listed(client: AsyncClient) -> None:
    response = await client.post(
        SEARCH, json={"ingredient_ids": ["potato", "salt"], "excluded_staples": []}
    )

    assert response.json()["ignored_ingredients"] == [
        {"id": "salt", "name": "Salt", "reason": "now_staple"}
    ]


async def test_recipe_detail(client: AsyncClient) -> None:
    card = (await client.post(SEARCH, json={"ingredient_ids": ["potato"]})).json()[
        "results"
    ][0]

    response = await client.get(f"/api/v1/recipes/{card['id']}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["id"] == card["id"]
    assert detail["name"] == card["name"]
    potato = next(item for item in detail["ingredients"] if item["id"] == "potato")
    assert potato["name"] == "Potato"
    assert potato["unit"] is not None
    assert potato["amount"] > 0
    assert 1 <= detail["serves"] <= 12
    assert len(detail["steps"]) >= 2
    assert detail["image"] is None


async def test_recipe_detail_marks_to_taste_ingredients(client: AsyncClient) -> None:
    jeera_aloo = "01a15175-3c01-7f7f-bbc8-f5c5fce48a60"

    detail = (await client.get(f"/api/v1/recipes/{jeera_aloo}")).json()

    salt = next(item for item in detail["ingredients"] if item["id"] == "salt")
    assert (salt["amount"], salt["unit"]) == (None, None)


@pytest.mark.parametrize("path", ["/api/v1/ingredients", "/api/v1/staples"])
async def test_catalog_lists_send_an_etag_and_honour_if_none_match(
    client: AsyncClient, path: str
) -> None:
    first = await client.get(path)
    etag = first.headers["etag"]

    again = await client.get(path, headers={"If-None-Match": etag})
    weak = await client.get(path, headers={"If-None-Match": f'"other", W/{etag}'})
    star = await client.get(path, headers={"If-None-Match": "*"})
    stale = await client.get(path, headers={"If-None-Match": '"sha256-old"'})

    assert first.status_code == 200
    assert first.headers["cache-control"] == "public, no-cache"
    assert etag.startswith('"sha256-')
    assert (again.status_code, again.content) == (304, b"")
    assert again.headers["etag"] == etag
    assert weak.status_code == star.status_code == 304
    assert stale.status_code == 200
    assert stale.content == first.content


async def test_etag_is_the_same_on_every_pod(make_app: AppFactory) -> None:
    """Two apps built from the same files must agree, or 304s never happen."""
    async with client_for(make_app()) as one, client_for(make_app()) as two:
        a = await one.get("/api/v1/ingredients")
        b = await two.get("/api/v1/ingredients")

    assert a.headers["etag"] == b.headers["etag"]
    assert a.content == b.content


async def test_ingredient_entry_shape(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/ingredients")).json()
    potato = next(i for i in body["ingredients"] if i["id"] == "potato")

    assert potato == {
        "id": "potato",
        "name": "Potato",
        "class": "A",
        "kind": None,
        "category": {"id": "vegetables", "name": potato["category"]["name"]},
        "diet": "vegan",
        "search_terms": potato["search_terms"],
    }


async def test_healthz(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert (response.status_code, response.json()) == (200, {"status": "ok"})


async def test_unknown_route_is_a_problem(client: AsyncClient) -> None:
    response = await client.get("/api/v1/nope")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
    }


async def test_wrong_method_is_a_problem_with_allow(client: AsyncClient) -> None:
    response = await client.post("/api/v1/staples")

    assert response.status_code == 405
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.headers["allow"] == "GET"


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
async def test_wrong_method_on_search_is_405_not_a_recipe_id(
    client: AsyncClient, method: str
) -> None:
    response = await client.request(method, SEARCH)

    assert response.status_code == 405
    assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
    assert response.headers["allow"] == "POST"


async def test_trailing_slash_is_not_redirected(client: AsyncClient) -> None:
    card = (await client.post(SEARCH, json={"ingredient_ids": ["potato"]})).json()[
        "results"
    ][0]

    response = await client.get(f"/api/v1/recipes/{card['id']}/")

    assert response.status_code == 404
    assert "location" not in response.headers
