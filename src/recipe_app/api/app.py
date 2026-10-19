"""The app factory and the composition root."""

import hashlib
import logging
import os
import time
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from recipe_app.api import presenters
from recipe_app.api.limits import BodySizeLimit
from recipe_app.api.problems import problem_media_types, register_problem_handlers
from recipe_app.api.routes import CachedBody, health_router, router
from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.infra.config import data_dir_from_env, signing_keys_from_env
from recipe_app.infra.data import load_catalog, load_recipes
from recipe_app.infra.logs import configure_logging
from recipe_app.infra.memory import InMemoryRecipeRepository
from recipe_app.services.search import RecipeService

logger = logging.getLogger(__name__)

API_VERSION = "1.0.0"


def create_app(*, catalog: IngredientCatalog, service: RecipeService) -> FastAPI:
    """Build the app around ready parts; tests call this with their own."""
    app = FastAPI(
        title="Pantry to Plate",
        version=API_VERSION,
        description=(
            "Recipes you can cook from what's in your kitchen. Clients must "
            "ignore response fields they don't recognise."
        ),
        debug=False,
        # No route ends in a slash, and a redirect would name this pod's own
        # host and scheme, not the load balancer's: a stray slash is a 404.
        redirect_slashes=False,
    )
    app.add_middleware(BodySizeLimit)
    app.state.service = service
    app.state.ingredients_body = _cache(presenters.ingredients_response(catalog))
    app.state.staples_body = _cache(presenters.staples_response(catalog))
    register_problem_handlers(app)
    app.include_router(router)
    app.include_router(health_router)
    _document_problems(app)
    return app


def _document_problems(app: FastAPI) -> None:
    build = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = problem_media_types(build())
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def build_app() -> FastAPI:
    """Load everything from the environment; refuse to start on any problem.

    Run with `uvicorn --factory recipe_app.api.app:build_app`.
    """
    configure_logging()
    data_dir = data_dir_from_env(os.environ)
    keys = signing_keys_from_env(os.environ)
    catalog = load_catalog(data_dir)
    recipes = load_recipes(catalog, data_dir)
    logger.info("loaded catalog %s with %d recipes", catalog.content_hash, len(recipes))
    service = RecipeService(
        catalog=catalog,
        repository=InMemoryRecipeRepository(recipes),
        keys=keys,
        clock=lambda: int(time.time()),
    )
    return create_app(catalog=catalog, service=service)


def _cache(model: BaseModel) -> CachedBody:
    # Field order is fixed by the model and the lists are sorted, so the
    # same catalog always gives the same bytes and the same ETag.
    body = model.model_dump_json().encode()
    return CachedBody(body=body, etag=f'"sha256-{hashlib.sha256(body).hexdigest()}"')
