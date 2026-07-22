"""
core/views/health.py
====================
Endpoint de verificación de salud (Health Check) para producción (Render).
Permite monitorear el estado en tiempo real del servidor Django y la base de datos MongoDB.
"""
from __future__ import annotations

import logging
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from core.database import MongoDBClient

logger = logging.getLogger(__name__)


@csrf_exempt
@require_GET
def health_check(request: HttpRequest) -> JsonResponse:
    """
    GET /api/v1/health/
    Verifica que la API esté activa y que MongoDB Atlas responda al ping.
    Devuelve 200 OK si todo está funcional o 503 Service Unavailable si MongoDB falla.
    """
    try:
        # get_database() verifica o inicializa la conexión singleton con MongoDB
        db = MongoDBClient.get_database()
        # Comando administrativo ping para comprobar respuesta en milisegundos
        client = MongoDBClient.get_client()
        client.admin.command("ping")

        return JsonResponse({
            "status": "ok",
            "service": "Tu-Turismo API REST",
            "mongodb": "connected",
            "database": db.name
        }, status=200)
    except Exception as exc:  # noqa: BLE001
        logger.critical("❌ Health Check falló: no hay conexión a MongoDB (%s)", exc)
        return JsonResponse({
            "status": "error",
            "service": "Tu-Turismo API REST",
            "mongodb": "disconnected",
            "detail": str(exc)
        }, status=503)
