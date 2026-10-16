"""The links between the docs pages point to real files."""

import re

from stylehub.common.config import ROOT


def test_relative_links_in_the_docs_point_to_real_files():
    link = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
    docs = ROOT / "docs"
    pages = [
        ROOT / "README.md",
        docs / "README.md",
        ROOT / "dbt" / "README.md",
        ROOT / "deploy" / "airflow" / "README.md",
    ]
    pages += sorted((docs / "design").glob("*.md")) + sorted((docs / "ops").glob("*.md"))
    broken = []
    for page in pages:
        for target in link.findall(page.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (page.parent / target).exists():
                broken.append(f"{page.relative_to(ROOT)} -> {target}")
    assert not broken, broken
