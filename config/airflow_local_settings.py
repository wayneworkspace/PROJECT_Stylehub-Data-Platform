"""Airflow logging: the default config plus a colored console formatter."""

from copy import deepcopy

from airflow.config_templates.airflow_local_settings import DEFAULT_LOGGING_CONFIG

LOGGING_CONFIG = deepcopy(DEFAULT_LOGGING_CONFIG)

LOGGING_CONFIG["formatters"]["colored_console"] = {
    "()": "colorlog.ColoredFormatter",
    "format": "%(log_color)s[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s",
    "log_colors": {
        "DEBUG": "cyan",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "red,bg_white",
    },
}
LOGGING_CONFIG["handlers"]["console"]["formatter"] = "colored_console"
