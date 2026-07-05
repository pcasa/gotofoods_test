from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "menu_sample.xml"


def test_ingest_endpoint_loads_menu(client, db, settings):
    settings.MENU_XML_PATH = str(FIXTURE)
    response = client.post("/internal/ingest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["categories"] == 3
    assert payload["products"] == 4


def test_cors_headers_for_browser_clients(client, db, settings):
    settings.CORS_ALLOW_ALL_ORIGINS = True
    response = client.get("/health", HTTP_ORIGIN="http://localhost:3000")
    assert response["Access-Control-Allow-Origin"] == "*"


def test_ingest_endpoint_rejects_get(client, db):
    assert client.get("/internal/ingest").status_code == 405


def test_ingest_endpoint_reports_missing_file(client, db, settings):
    settings.MENU_XML_PATH = "/nonexistent/menu.xml"
    response = client.post("/internal/ingest")
    assert response.status_code == 500
    assert "not found" in response.json()["error"]
