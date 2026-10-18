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


def today() -> str:
    return f"{datetime.now(UTC):%Y-%m-%d}"


class DailyFileHandler(logging.FileHandler):
    """Plain file named by UTC day; moves to a new file after midnight."""

    def __init__(self, stem: str) -> None:
        self.stem, self.day = stem, today()
        super().__init__(LOG_DIR / f"{stem}_{self.day}.log", encoding="utf-8", delay=True)

    def emit(self, record: logging.LogRecord) -> None:
        if (day := today()) != self.day:  # long runs like the dashboard
            self.close()  # the next write opens the new day's file
            self.day, self.baseFilename = day, str(LOG_DIR / f"{self.stem}_{day}.log")
        super().emit(record)


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
    file = DailyFileHandler(f"unified-data_{env}_{module_name}")
    file.setFormatter(logging.Formatter(FORMAT))

    logger.addHandler(console)
    logger.addHandler(file)
    return logger
