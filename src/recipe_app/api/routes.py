"""The v1 routes. Each one validates, calls the service and translates."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from recipe_app.api import presenters
from recipe_app.api.problems import RecipeNotFoundError, problem_responses
from recipe_app.api.schemas import (
    Health,
    IngredientsResponse,
    RecipeDetail,
    SearchRequest,
    SearchResponse,
    StaplesResponse,
)
from recipe_app.services.search import RecipeService, SearchQuery

JSON = "application/json"
# Store it, but ask before reusing it: a changed catalog is seen on the next load.
CATALOG_CACHE_CONTROL = "public, no-cache"
IF_NONE_MATCH_DOC = {
    "parameters": [
        {
            "name": "If-None-Match",
            "in": "header",
            "required": False,
            "schema": {"type": "string"},
            "description": "The ETag from the last response; 304 if unchanged.",
        }
    ]
}


@dataclass(frozen=True, slots=True)
class CachedBody:
    """A response serialized once at startup, so every pod sends the same ETag."""

    body: bytes
    etag: str


def get_service(request: Request) -> RecipeService:
    service: RecipeService = request.app.state.service
    return service


def get_ingredients_body(request: Request) -> CachedBody:
    body: CachedBody = request.app.state.ingredients_body
    return body


def get_staples_body(request: Request) -> CachedBody:
    body: CachedBody = request.app.state.staples_body
    return body


Service = Annotated[RecipeService, Depends(get_service)]

router = APIRouter(prefix="/api/v1")
health_router = APIRouter()


@router.post(
    "/recipes/search",
    tags=["recipes"],
    response_model=SearchResponse,
    responses=problem_responses(413, 422, 500),
)
async def search_recipes(request: SearchRequest, service: Service) -> SearchResponse:
    """One swipe deck. Follow `next_cursor`, unchanged, for the next deck."""
    result = await service.search(
        SearchQuery(
            ingredient_ids=request.ingredient_ids,
            excluded_staples=request.excluded_staples,
            diet=request.diet,
            max_total_minutes=request.max_total_minutes,
            hidden_recipe_ids=frozenset(request.hidden_recipe_ids),
            limit=request.limit,
            cursor=request.cursor,
        )
    )
    return presenters.search_response(result)


@router.api_route(
    "/recipes/search",
    methods=["GET", "HEAD", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
async def search_wrong_method() -> None:
    """Without this, GET /recipes/search matches /recipes/{recipe_id}: a 422."""
    raise StarletteHTTPException(405, headers={"Allow": "POST"})


@router.get(
    "/recipes/{recipe_id}",
    tags=["recipes"],
    response_model=RecipeDetail,
    responses=problem_responses(404, 422, 500),
)
async def get_recipe(recipe_id: UUID, service: Service) -> RecipeDetail:
    detail = await service.get_detail(recipe_id)
    if detail is None:
        raise RecipeNotFoundError(recipe_id)
    return presenters.recipe_detail(detail)


@router.get(
    "/ingredients",
    tags=["catalog"],
    response_model=IngredientsResponse,
    responses={304: {"description": "Not Modified"}, **problem_responses(500)},
    openapi_extra=IF_NONE_MATCH_DOC,
)
async def list_ingredients(
    request: Request, cached: Annotated[CachedBody, Depends(get_ingredients_body)]
) -> Response:
    """Every live ingredient for the picker. Send `If-None-Match` on every load."""
    return _cached_response(cached, request.headers.get("if-none-match"))


@router.get(
    "/staples",
    tags=["catalog"],
    response_model=StaplesResponse,
    responses={304: {"description": "Not Modified"}, **problem_responses(500)},
    openapi_extra=IF_NONE_MATCH_DOC,
)
async def list_staples(
    request: Request, cached: Annotated[CachedBody, Depends(get_staples_body)]
) -> Response:
    """Live staples by kind, then category, for the staples screen."""
    return _cached_response(cached, request.headers.get("if-none-match"))


@health_router.get(
    "/healthz", tags=["ops"], response_model=Health, responses=problem_responses(500)
)
async def healthz() -> Health:
    """Liveness only: the process is up. Readiness comes in Task 5."""
    return Health(status="ok")


def _cached_response(cached: CachedBody, if_none_match: str | None) -> Response:
    # Read from the raw headers, not a Header() parameter: no header value can
    # fail validation, so these routes have no 422 to document.
    headers = {"ETag": cached.etag, "Cache-Control": CATALOG_CACHE_CONTROL}
    if if_none_match is not None and _matches(if_none_match, cached.etag):
        return Response(status_code=304, headers=headers)
    return Response(content=cached.body, media_type=JSON, headers=headers)


def _matches(if_none_match: str, etag: str) -> bool:
    """RFC 9110 weak comparison, which If-None-Match uses."""
    if if_none_match.strip() == "*":
        return True
    candidates = (tag.strip().removeprefix("W/") for tag in if_none_match.split(","))
    return etag in candidates
