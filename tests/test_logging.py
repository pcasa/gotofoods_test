import logging
from pathlib import Path

from apps.menu.services.ingest import MenuIngestService
from core import observability

FIXTURE = Path(__file__).parent / "fixtures" / "menu_sample.xml"


def test_info_emits_event_with_context(caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        observability.info("something_happened", count=3, source="unit-test")
    record = caplog.records[-1]
    assert record.name == "app"
    assert record.message == "something_happened count=3 source=unit-test"


def test_error_carries_exception_info(caplog):
    with caplog.at_level(logging.ERROR, logger="app"):
        try:
            raise ValueError("boom")
        except ValueError as exc:
            observability.error("something_failed", exc=exc, stage="unit-test")
    record = caplog.records[-1]
    assert record.levelno == logging.ERROR
    assert record.exc_info[0] is ValueError
    assert "stage=unit-test" in record.message


def test_ingest_logs_completion_event(db, caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        MenuIngestService().ingest(FIXTURE)
    messages = [r.message for r in caplog.records if r.name == "app"]
    completed = [m for m in messages if m.startswith("menu_ingest_completed")]
    assert len(completed) == 1
    assert "products=4" in completed[0]
