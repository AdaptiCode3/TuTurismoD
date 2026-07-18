"""core/views/backup.py — Exportación de colecciones MongoDB en formato JSON."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.database import MongoDBClient
from core.security import jwt_required

logger = logging.getLogger(__name__)

EXPORTABLE_COLLECTIONS = {
    "places":       "lugares",
    "lugares":      "lugares",
    "restaurants":  "restaurantes",
    "restaurantes": "restaurantes",
    "events":       "eventos",
    "eventos":      "eventos",
    "users":        "users",
    "usuarios":     "users",
    "categorias":   "categorias",
    "all":          None,
    "full":         None,
}


def _serialize_doc(doc: dict) -> dict:
    """Convierte ObjectId a string para que sea serializable a JSON."""
    result = {}
    for k, v in doc.items():
        if k == "_id":
            result["id"] = str(v)
        elif hasattr(v, "__str__") and type(v).__name__ == "ObjectId":
            result[k] = str(v)
        else:
            result[k] = v
    return result


def _export_collection(db, mongo_name: str) -> list[dict]:
    try:
        return [_serialize_doc(doc) for doc in db[mongo_name].find({})]
    except Exception as exc:
        logger.warning("Error exportando colección '%s': %s", mongo_name, exc)
        return []


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def backup_export(request: HttpRequest, resource: str = "all") -> HttpResponse:
    """
    GET /api/v1/core/admin/backup/<resource>/

    Exporta una colección (o todas) como archivo JSON descargable.
    resource: "places" | "restaurants" | "events" | "users" | "all"
    Requiere rol admin.
    """
    payload = getattr(request, "user_payload", {})
    if payload.get("rol") != "admin":
        return JsonResponse({"error": "Acceso denegado.", "detail": "Se requiere rol admin."}, status=403)

    if resource not in EXPORTABLE_COLLECTIONS:
        return JsonResponse(
            {"error": f"Recurso '{resource}' no válido.",
             "detail": f"Opciones: {list(EXPORTABLE_COLLECTIONS.keys())}"},
            status=400,
        )

    try:
        db = MongoDBClient.get_database()
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en backup_export: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

    if resource in ("all", "full"):
        payload_data: dict = {}
        unique_collections = {"lugares", "restaurantes", "eventos", "users", "categorias"}
        for mongo_name in unique_collections:
            payload_data[mongo_name] = _export_collection(db, mongo_name)
        filename = f"tuturismo_backup_completo_{timestamp}.json"
    else:
        mongo_name = EXPORTABLE_COLLECTIONS[resource]
        payload_data = {resource: _export_collection(db, mongo_name)}
        filename = f"tuturismo_{resource}_{timestamp}.json"

    json_bytes = json.dumps(payload_data, ensure_ascii=False, indent=2).encode("utf-8")

    response = HttpResponse(json_bytes, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = str(len(json_bytes))
    return response
