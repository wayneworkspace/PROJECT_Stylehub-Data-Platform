"""One way to set up logging for the command-line steps: the message only, on stdout."""

import logging
import sys

PIPELINE_FORMAT = "%(asctime)s %(levelname)s %(message)s"  # the pipeline steps also show the time


def setup_cli_logging(fmt: str = "%(message)s") -> None:
    """Make log.info(...) show up in the terminal, like the print calls it replaces."""
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format=fmt)
