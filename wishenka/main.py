"""Server entrypoint for Wishenka application."""

import logging

import uvicorn

from wishenka.config import Settings
from wishenka.logging import configure_logging
from wishenka.web.app import create_app

settings = Settings()
configure_logging(log_level=settings.log_level, json_logs=settings.log_json)
app = create_app(settings)


def main() -> None:
    """Run uvicorn server with application settings."""
    logger = logging.getLogger("wishenka.main")
    logger.info("Starting Wishenka server on http://0.0.0.0:8000")
    uvicorn.run(
        "wishenka.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug or settings.environment == "development",
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
