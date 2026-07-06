"""Count reconciliation against the real 17 MB feed.

Exists because fixture-only testing has already missed real-data structure
once (the <singleusecategories> section — 160 of 161 products). Marked slow:
excluded from the local fast loop, run explicitly in CI (`pytest -m slow`).
"""

from pathlib import Path

import pytest

from apps.menu.services.ingest import MenuIngestService

REAL_FILE = Path(__file__).parent.parent / "24405.xml"


@pytest.mark.slow
def test_real_feed_ingests_completely(db):
    result = MenuIngestService().ingest(REAL_FILE)
    assert result.skipped is False
    assert result.categories == 22
    assert result.products == 161
    assert result.option_groups == 4542
    assert result.options == 24231
    assert result.ingredients == 127
