"""
core/views/core_views.py
========================
Vistas base de la aplicación core.

NOTA ARQUITECTÓNICA: No se importa ni usa django.db.models.
Toda interacción con la base de datos se hace a través de MongoDBClient.
"""
import json
from typing import Any

from django.http import HttpRequest, JsonResponse
from pymongo.errors import ConnectionFailure

from core.database import MongoDBClient


def health_check(request: HttpRequest) -> JsonResponse:
    """
    GET /api/v1/core/health/

    Endpoint de comprobación de salud del sistema.
    Verifica que Django está en línea y que la conexión a MongoDB es válida.

    Respuestas:
        200 OK          → Todo operativo.
        503 Unavailable → MongoDB no disponible.
    """
    status: dict[str, Any] = {
        "django": "ok",
        "mongodb": "unknown",
        "database": None,
    }

    try:
        db = MongoDBClient.get_database()
        # Ejecutamos un 'ping' para confirmar la conectividad en tiempo real
        db.command("ping")
        status["mongodb"] = "ok"
        status["database"] = db.name
        return JsonResponse(status, status=200)

    except RuntimeError as exc:
        # MongoDB no disponible (instancia no inicializada)
        status["mongodb"] = "unavailable"
        status["error"] = str(exc)
        return JsonResponse(status, status=503)

    except ConnectionFailure as exc:
        # MongoDB responde pero hay un error de conexión en tiempo de ejecución
        status["mongodb"] = "connection_error"
        status["error"] = str(exc)
        return JsonResponse(status, status=503)
