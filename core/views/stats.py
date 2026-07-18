"""core/views/stats.py — Estadísticas del sistema para el panel admin."""
from __future__ import annotations

import logging

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.database import MongoDBClient
from core.security import jwt_required

logger = logging.getLogger(__name__)

COLLECTIONS = {
    "lugares":      "lugars",
    "restaurantes": "restaurantes",
    "eventos":      "eventos",
    "usuarios":     "users",
    "favoritos":    "favorites",
}


def _count(db, collection: str, query: dict = None) -> int:
    try:
        return db[collection].count_documents(query or {})
    except Exception as exc:
        logger.warning("count_documents(%s) falló: %s", collection, exc)
        return 0


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def admin_stats(request: HttpRequest) -> JsonResponse:
    """
    GET /api/v1/core/admin/stats/

    Requiere rol admin. Devuelve conteos de colecciones y distribución por rol.
    """
    payload = getattr(request, "user_payload", {})
    if payload.get("rol") != "admin":
        return JsonResponse({"error": "Acceso denegado.", "detail": "Se requiere rol admin."}, status=403)

    try:
        db = MongoDBClient.get_database()
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en admin_stats: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)

    total_lugares      = _count(db, COLLECTIONS["lugares"],      {"activo": {"$ne": False}})
    total_restaurantes = _count(db, COLLECTIONS["restaurantes"],  {"activo": {"$ne": False}})
    total_eventos      = _count(db, COLLECTIONS["eventos"],       {"activo": {"$ne": False}})
    total_usuarios     = _count(db, COLLECTIONS["usuarios"])
    total_favoritos    = _count(db, COLLECTIONS["favoritos"])

    # Distribución de roles mediante aggregation
    roles: dict[str, int] = {}
    try:
        pipeline = [{"$group": {"_id": "$rol", "count": {"$sum": 1}}}]
        for doc in db[COLLECTIONS["usuarios"]].aggregate(pipeline):
            roles[str(doc["_id"] or "sin_rol")] = doc["count"]
    except Exception as exc:
        logger.warning("Aggregation de roles falló: %s", exc)

    return JsonResponse({
        "success": True,
        "data": {
            "totales": {
                "lugares":      total_lugares,
                "restaurantes": total_restaurantes,
                "eventos":      total_eventos,
                "usuarios":     total_usuarios,
                "favoritos":    total_favoritos,
            },
            "roles":             roles,
            "tasa_crecimiento":  0,
            "alertas_pendientes": 0,
        },
    }, status=200)
