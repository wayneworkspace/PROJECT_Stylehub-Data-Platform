"""Fill the placeholders of a SQL file: ${project}, ${bronze}, ${silver}, ${gold}, ${ops}, ..."""

from pathlib import Path
from string import Template

from stylehub.common.config import Settings, resolve


def render_sql(path: Path, cfg: Settings | None = None) -> str:
    """Read a SQL file and substitute the placeholders with the settings.

    A placeholder that has no setting raises KeyError, so a typo is found before BigQuery runs it.
    """
    return Template(path.read_text(encoding="utf-8")).substitute(resolve(cfg).model_dump())
