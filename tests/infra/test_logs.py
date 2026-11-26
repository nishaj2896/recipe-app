"""JSON log lines (ADR-0013 rule 4)."""

import json
import logging
import sys
from collections.abc import Iterator

import pytest

from recipe_app.infra.logs import (
    REQUEST_ID,
    JsonFormatter,
    TextFormatter,
    configure_logging,
)


def record(
    message: str = "hello %s", *args: object, **extra: object
) -> logging.LogRecord:
    made = logging.LogRecord(
        "recipe_app.x", logging.INFO, __file__, 1, message, args, None
    )
    made.__dict__.update(extra)
    return made


@pytest.fixture
def request_id() -> Iterator[str]:
    token = REQUEST_ID.set("0193b2a4-req")
    yield "0193b2a4-req"
    REQUEST_ID.reset(token)


def test_a_line_is_one_json_object() -> None:
    line = JsonFormatter().format(record("hello %s", "world"))

    entry = json.loads(line)
    assert "\n" not in line
    assert entry["message"] == "hello world"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "recipe_app.x"
    assert entry["time"].endswith("Z")
    assert "request_id" not in entry


def test_the_request_id_rides_along(request_id: str) -> None:
    entry = json.loads(JsonFormatter().format(record()))

    assert entry["request_id"] == request_id


def test_fields_are_added_but_never_replace_the_core_keys() -> None:
    made = record(fields={"route": "/x", "status": 200, "message": "forged"})

    entry = json.loads(JsonFormatter().format(made))

    assert entry["route"] == "/x"
    assert entry["status"] == 200
    assert entry["message"] == "hello %s"


def test_other_record_attributes_are_not_copied() -> None:
    entry = json.loads(JsonFormatter().format(record(stray="leaked-value")))

    assert "leaked-value" not in json.dumps(entry)


def test_an_exception_gives_its_type_and_traceback() -> None:
    try:
        raise ValueError("nope")
    except ValueError:
        made = logging.LogRecord(
            "recipe_app.x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )

    entry = json.loads(JsonFormatter().format(made))

    assert entry["exc_type"] == "ValueError"
    assert "Traceback" in entry["traceback"]


def test_text_lines_end_with_the_request_id(request_id: str) -> None:
    line = TextFormatter().format(record())

    assert line.endswith(f"INFO recipe_app.x: hello %s [{request_id}]")


@pytest.fixture
def fresh_loggers() -> Iterator[None]:
    names = ("recipe_app", "uvicorn", "uvicorn.access", "sqlalchemy", "asyncpg")
    loggers = [logging.getLogger(name) for name in names]
    saved = [(lg.handlers[:], lg.level, lg.propagate, lg.disabled) for lg in loggers]
    for lg in loggers:
        lg.handlers.clear()
    yield
    for lg, (handlers, level, propagate, disabled) in zip(loggers, saved, strict=True):
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate = propagate
        lg.disabled = disabled


@pytest.mark.usefixtures("fresh_loggers")
def test_configure_is_idempotent() -> None:
    configure_logging()
    configure_logging()

    assert len(logging.getLogger("recipe_app").handlers) == 1
    assert len(logging.getLogger("uvicorn").handlers) == 1


@pytest.mark.usefixtures("fresh_loggers")
def test_uvicorn_writes_json_and_its_access_log_is_off(
    capfd: pytest.CaptureFixture[str],
) -> None:
    configure_logging()

    logging.getLogger("uvicorn.error").info("Started server process")
    logging.getLogger("uvicorn.access").info("GET / 200")

    lines = [json.loads(line) for line in capfd.readouterr().out.splitlines()]
    assert [line["message"] for line in lines] == ["Started server process"]


@pytest.mark.usefixtures("fresh_loggers")
def test_the_level_applies(capfd: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING")

    logging.getLogger("recipe_app.x").info("quiet")
    logging.getLogger("recipe_app.x").warning("loud")

    assert "quiet" not in capfd.readouterr().out
