"""The app factory and the composition root."""

import hashlib
import logging
import os
import time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from recipe_app.api import presenters
from recipe_app.api.limits import BodySizeLimit
from recipe_app.api.problems import problem_media_types, register_problem_handlers
from recipe_app.api.routes import CachedBody, health_router, router
from recipe_app.domain.catalog import IngredientCatalog
from recipe_app.infra.catalog_store import read_catalog
from recipe_app.infra.config import database_url_from_env, signing_keys_from_env
from recipe_app.infra.database import create_engine
from recipe_app.infra.logs import configure_logging
from recipe_app.infra.postgres import PostgresRecipeRepository
from recipe_app.services.search import RecipeService

logger = logging.getLogger(__name__)

API_VERSION = "1.0.0"


Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(*, catalog: IngredientCatalog, service: RecipeService) -> FastAPI:
    """Build the app around ready parts; tests call this with their own."""
    app = _new_app()
    _serve(app, catalog, service)
    return app


def openapi_schema() -> dict[str, Any]:
    """The API's OpenAPI document; the web app generates its types from it."""
    return _new_app().openapi()


def _new_app(lifespan: Lifespan | None = None) -> FastAPI:
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
        lifespan=lifespan,
    )
    app.add_middleware(BodySizeLimit)
    register_problem_handlers(app)
    app.include_router(router)
    app.include_router(health_router)
    _document_problems(app)
    return app


def _serve(app: FastAPI, catalog: IngredientCatalog, service: RecipeService) -> None:
    """Hand the routes what they read from app.state."""
    app.state.service = service
    app.state.ingredients_body = _cache(presenters.ingredients_response(catalog))
    app.state.staples_body = _cache(presenters.staples_response(catalog))


def _document_problems(app: FastAPI) -> None:
    build = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = problem_media_types(build())
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def build_app() -> FastAPI:
    """Read the settings now and the database at startup; refuse to start on
    any problem (ADR-0005 rule 7).

    Run with `uvicorn --factory recipe_app.api.app:build_app`. Settings fail
    here, before the server binds; a missing or unsynced database fails the
    lifespan startup, which stops uvicorn the same way.
    """
    configure_logging()
    keys = signing_keys_from_env(os.environ)
    url = database_url_from_env(os.environ)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # One pool per process, opened and closed with the app.
        engine = create_engine(url)
        try:
            catalog = await read_catalog(engine)
            logger.info(
                "loaded catalog %s with %d ingredients from the database",
                catalog.content_hash,
                len(catalog.by_id),
            )
            service = RecipeService(
                catalog=catalog,
                repository=PostgresRecipeRepository(engine, catalog),
                keys=keys,
                clock=lambda: int(time.time()),
            )
            _serve(app, catalog, service)
            yield
        finally:
            await engine.dispose()

    return _new_app(lifespan)


def _cache(model: BaseModel) -> CachedBody:
    # Field order is fixed by the model and the lists are sorted, so the
    # same catalog always gives the same bytes and the same ETag.
    body = model.model_dump_json().encode()
    return CachedBody(body=body, etag=f'"sha256-{hashlib.sha256(body).hexdigest()}"')
