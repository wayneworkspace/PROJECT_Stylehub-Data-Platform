"""Shared logger: colors in the terminal only, plain daily files."""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import colorlog

LOG_DIR = Path(__file__).resolve().parents[2] / "logs" / "custom_scripts"
FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
COLORS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "red,bg_white",
}


def get_logger(module_name: str, env: str | None = None) -> logging.Logger:
    """Logger writing to the terminal and logs/custom_scripts; one setup per name."""
    logger = logging.getLogger(module_name)
    if logger.handlers:  # avoid duplicate handlers when called again
        return logger
    env = env or os.environ.get("STYLEHUB_ENV", "prod")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # our handlers only, no double lines

    console = logging.StreamHandler()
    # stream: no color codes when output is not a terminal (Airflow task logs).
    console.setFormatter(
        colorlog.ColoredFormatter(
            f"%(log_color)s{FORMAT}", log_colors=COLORS, stream=console.stream
        )
    )
    day = datetime.now(UTC).date()
    file = logging.FileHandler(
        LOG_DIR / f"unified-data_{env}_{module_name}_{day:%Y-%m-%d}.log", encoding="utf-8"
    )
    file.setFormatter(logging.Formatter(FORMAT))

    logger.addHandler(console)
    logger.addHandler(file)
    return logger
