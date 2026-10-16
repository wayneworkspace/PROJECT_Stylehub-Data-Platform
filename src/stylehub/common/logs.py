"""One way to set up logging for the command-line steps: the message only, on stdout."""

import logging
import sys


def setup_cli_logging() -> None:
    """Make log.info(...) show up in the terminal, like the print calls it replaces."""
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
