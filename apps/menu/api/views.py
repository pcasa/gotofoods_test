from dataclasses import asdict
from pathlib import Path

from django.conf import settings
from django.db import OperationalError, connection
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.menu.models import Category, Option, Product
from apps.menu.services.ingest import MenuIngestService
from core import observability


def health(request: HttpRequest) -> JsonResponse:
    try:
        connection.ensure_connection()
        counts = {
            "categories": Category.objects.count(),
            "products": Product.objects.count(),
            "options": Option.objects.count(),
        }
    except OperationalError as exc:
        observability.warning("health_degraded", database="unavailable", detail=str(exc))
        return JsonResponse({"status": "degraded", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ok", "database": "ok", "counts": counts})


@csrf_exempt
@require_POST
def trigger_ingest(request: HttpRequest) -> JsonResponse:
    """Re-run the idempotent menu ingest ("menu update" story for the demo).

    Unauthenticated by design for this exercise; in production this would sit
    behind admin auth or be replaced by a feed-driven worker (DESIGN.md D5).
    """
    xml_path = Path(settings.MENU_XML_PATH)
    if not xml_path.exists():
        observability.error("menu_ingest_source_missing", path=str(xml_path))
        return JsonResponse({"error": f"menu file not found: {xml_path}"}, status=500)
    result = MenuIngestService().ingest(xml_path)
    return JsonResponse(asdict(result))
