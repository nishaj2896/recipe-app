"""RFC 9457 problem details for every error, and the handlers that send them.

No handler puts exception text or a traceback in a body. Reasons a client
can't act on (why a cursor was refused, what crashed) go to the log only.
"""

import logging
import re
from collections.abc import Sequence
from http import HTTPStatus
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from recipe_app.api.schemas import FieldError, Problem
from recipe_app.domain.cursor import ExpiredCursorError, InvalidCursorError
from recipe_app.domain.matching import PantryError

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"
INVALID_CURSOR = "/problems/invalid-cursor"
CURSOR_EXPIRED = "/problems/cursor-expired"
_REQUEST_LOCATIONS = frozenset({"body", "path", "query", "header", "cookie"})
# A 50-item list can fail 50 ways; past this many, more errors don't help.
MAX_ERRORS = 20
_SAFE_NAME = re.compile(r"[a-z_][a-z0-9_]{0,63}")
# Pydantic messages that quote part of the input get a fixed text instead.
_FIXED_MESSAGES = {
    "json_invalid": "Request body is not valid JSON",
    "uuid_parsing": "Input should be a valid UUID",
}


class RecipeNotFoundError(LookupError):
    def __init__(self, recipe_id: UUID) -> None:
        super().__init__(recipe_id)
        self.recipe_id = recipe_id


def problem_response(problem: Problem) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(mode="json", exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_MEDIA_TYPE,
    )


def invalid_request(errors: list[FieldError]) -> Problem:
    """Sends the first MAX_ERRORS errors; `detail` still counts all of them."""
    noun = "field" if len(errors) == 1 else "fields"
    shown = "" if len(errors) <= MAX_ERRORS else f" The first {MAX_ERRORS} are listed."
    return Problem(
        title="Invalid request",
        status=422,
        detail=f"{len(errors)} {noun} failed validation.{shown}",
        errors=errors[:MAX_ERRORS],
    )


def field_path(loc: Sequence[int | str]) -> str:
    """("body", "ingredient_ids", 0) -> "ingredient_ids[0]".

    A name that isn't a plain identifier came from the client (an unknown
    key), so it is never echoed: the path is just "body".
    """
    parts = list(loc[1:] if loc and loc[0] in _REQUEST_LOCATIONS else loc)
    path = ""
    for part in parts:
        if isinstance(part, str) and not _SAFE_NAME.fullmatch(part):
            return "body"
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}" if path else str(part)
    return path or "body"


def register_problem_handlers(app: FastAPI) -> None:
    # The decorator accepts handlers typed with their own exception class.
    app.exception_handler(RequestValidationError)(_validation)
    app.exception_handler(PantryError)(_pantry)
    app.exception_handler(InvalidCursorError)(_invalid_cursor)
    app.exception_handler(ExpiredCursorError)(_expired_cursor)
    app.exception_handler(RecipeNotFoundError)(_not_found)
    app.exception_handler(StarletteHTTPException)(_http)
    app.exception_handler(Exception)(_unhandled)


async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    raw: Sequence[Any] = exc.errors()
    errors = [_field_error(error) for error in raw]
    problem = invalid_request(errors)
    if errors and all(error.field == "cursor" for error in errors):
        # A cursor that is too long fails here, before the domain sees it, but
        # it is still an invalid cursor (ADR-0003 rule 9), logged like the rest.
        logger.warning("invalid cursor: failed request validation")
        problem = _cursor_problem(INVALID_CURSOR)
    return problem_response(problem)


def _field_error(error: Any) -> FieldError:
    # "input" and "ctx" can hold what the client sent, so only "msg" is used,
    # and the few messages that quote the input are replaced.
    if error["type"] == "json_invalid":
        return FieldError(field="body", message=_FIXED_MESSAGES["json_invalid"])
    message = _FIXED_MESSAGES.get(error["type"], error["msg"])
    return FieldError(field=field_path(error["loc"]), message=message)


async def _pantry(_: Request, exc: PantryError) -> JSONResponse:
    errors = []
    for text in exc.problems:
        # The domain writes "<field>: <message>"; the ids in it passed the slug check.
        field, _sep, message = text.partition(": ")
        errors.append(FieldError(field=field, message=message))
    return problem_response(invalid_request(errors))


async def _invalid_cursor(_: Request, exc: InvalidCursorError) -> JSONResponse:
    logger.warning("invalid cursor: %s", exc)
    return problem_response(_cursor_problem(INVALID_CURSOR))


async def _expired_cursor(_: Request, exc: ExpiredCursorError) -> JSONResponse:
    logger.info("expired cursor: %s", exc)
    return problem_response(_cursor_problem(CURSOR_EXPIRED))


def _cursor_problem(problem_type: str) -> Problem:
    if problem_type == CURSOR_EXPIRED:
        return Problem(
            type=CURSOR_EXPIRED,
            title="Cursor expired",
            status=422,
            detail="Search again without a cursor to get the first deck.",
        )
    return Problem(
        type=INVALID_CURSOR,
        title="Invalid cursor",
        status=422,
        detail="Send the next_cursor from the previous response unchanged.",
    )


async def _not_found(_: Request, exc: RecipeNotFoundError) -> JSONResponse:
    return problem_response(
        Problem(
            title="Recipe not found",
            status=404,
            detail=f"No recipe exists with id {exc.recipe_id}.",
        )
    )


async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    response = problem_response(
        Problem(title=HTTPStatus(exc.status_code).phrase, status=exc.status_code)
    )
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error", exc_info=exc)
    return problem_response(
        Problem(
            title="Internal Server Error",
            status=500,
            detail="Something went wrong on our side. Try again later.",
        )
    )


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI entries so every error status is documented with Problem.

    FastAPI files the model under application/json; problem_media_types
    moves it to application/problem+json once the schema is built.
    """
    return {
        status: {"model": Problem, "description": HTTPStatus(status).phrase}
        for status in statuses
    }


def problem_media_types(schema: dict[str, Any]) -> dict[str, Any]:
    """Document every 4xx and 5xx body as application/problem+json."""
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            for status, response in operation.get("responses", {}).items():
                content = response.get("content", {})
                if status[0] in "45" and "application/json" in content:
                    content[PROBLEM_MEDIA_TYPE] = content.pop("application/json")
    return schema
