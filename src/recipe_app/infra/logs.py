"""Plain stderr logging for recipe_app until Task 4 adds structured JSON logs."""

import logging

FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent: a second call, or a handler a host already added, is kept."""
    app_logger = logging.getLogger("recipe_app")
    app_logger.setLevel(level)
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(FORMAT))
        app_logger.addHandler(handler)
