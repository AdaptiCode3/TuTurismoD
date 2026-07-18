"""core/views/admin.py — CRUD admin para Lugares, Restaurantes y Eventos."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.repositories.events import EventRepository
from core.repositories.places import PlaceRepository
from core.repositories.restaurants import RestaurantRepository
from core.security import jwt_required

logger = logging.getLogger(__name__)

ADMIN_ROLE = "admin"

RESOURCE_MAP = {
    "places":      ("core.repositories.places",       "PlaceRepository",      "create_place",      "update_place",      "delete_place"),
    "restaurants": ("core.repositories.restaurants",  "RestaurantRepository", "create_restaurant", "update_restaurant", "delete_restaurant"),
    "events":      ("core.repositories.events",        "EventRepository",      "create_event",      "update_event",      "delete_event"),
}


def _get_repo(resource: str):
    """Resuelve y devuelve la clase del repositorio para el recurso dado."""
    if resource not in RESOURCE_MAP:
        return None
    module_path, class_name, *_ = RESOURCE_MAP[resource]
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _parse_body(request: HttpRequest) -> tuple[dict[str, Any], JsonResponse | None]:
    data: dict[str, Any] = {}
    content_type = getattr(request, "content_type", "") or request.META.get("CONTENT_TYPE", "")
    if "multipart/form-data" in content_type:
        if request.method in ["PUT", "PATCH"]:
            from django.http.multipartparser import MultiPartParser
            parser = MultiPartParser(request.META, request, request.upload_handlers)
            post, files = parser.parse()
            data = post.dict()
        else:
            data = request.POST.dict()
    else:
        try:
            body = request.body.decode("utf-8").strip()
            if not body:
                return {}, JsonResponse({"error": "Body vacío."}, status=400)
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}, JsonResponse({"error": "JSON inválido."}, status=400)

    # Normalizar coordenadas GeoJSON y planas
    lat = data.get("latitud")
    lng = data.get("longitud")
    if lat is not None and lng is not None and str(lat).strip() != "" and str(lng).strip() != "":
        try:
            f_lat = float(lat)
            f_lng = float(lng)
            data["ubicacion"] = {"type": "Point", "coordinates": [f_lng, f_lat]}
            data["coordenadas"] = {"lat": f_lat, "lng": f_lng}
            data["latitud"] = f_lat
            data["longitud"] = f_lng
        except (ValueError, TypeError):
            pass

    # Normalizar rating/calificación para uniformidad entre colecciones
    rating = data.get("rating")
    if rating is not None and str(rating).strip() != "":
        try:
            f_rating = float(rating)
            data["rating"] = f_rating
            data["calificacion"] = f_rating
            data["rating_promedio"] = f_rating
        except (ValueError, TypeError):
            pass

    return data, None


def _check_admin(request: HttpRequest) -> JsonResponse | None:
    payload = getattr(request, "user_payload", {})
    if payload.get("rol") != ADMIN_ROLE:
        return JsonResponse({"error": "Acceso denegado.", "detail": "Se requiere rol admin."}, status=403)
    return None


# ---------------------------------------------------------------------------
# POST /api/v1/core/admin/<resource>/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def resource_create(request: HttpRequest, resource: str) -> JsonResponse:
    if (err := _check_admin(request)):
        return err
    if resource not in RESOURCE_MAP:
        return JsonResponse({"error": f"Recurso '{resource}' no existe."}, status=404)

    data, err = _parse_body(request)
    if err:
        return err
    if not data:
        return JsonResponse({"error": "Body vacío o sin campos."}, status=400)

    _, _, create_method, _, _ = RESOURCE_MAP[resource]
    try:
        repo = _get_repo(resource)()
        doc = getattr(repo, create_method)(data)
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en admin create: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)

    if doc is None:
        return JsonResponse({"error": "No se pudo crear el recurso."}, status=400)

    return JsonResponse({"success": True, "data": asdict(doc)}, status=201)


# ---------------------------------------------------------------------------
# PUT/PATCH /api/v1/core/admin/<resource>/<resource_id>/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
def resource_update(request: HttpRequest, resource: str, resource_id: str) -> JsonResponse:
    if (err := _check_admin(request)):
        return err
    if resource not in RESOURCE_MAP:
        return JsonResponse({"error": f"Recurso '{resource}' no existe."}, status=404)

    data, err = _parse_body(request)
    if err:
        return err

    _, _, _, update_method, _ = RESOURCE_MAP[resource]
    try:
        repo = _get_repo(resource)()
        doc = getattr(repo, update_method)(resource_id, data)
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en admin update: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)

    if doc is None:
        return JsonResponse({"error": "Recurso no encontrado."}, status=404)

    return JsonResponse({"success": True, "data": asdict(doc)}, status=200)


# ---------------------------------------------------------------------------
# DELETE /api/v1/core/admin/<resource>/<resource_id>/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
def resource_delete(request: HttpRequest, resource: str, resource_id: str) -> JsonResponse:
    if (err := _check_admin(request)):
        return err
    if resource not in RESOURCE_MAP:
        return JsonResponse({"error": f"Recurso '{resource}' no existe."}, status=404)

    _, _, _, _, delete_method = RESOURCE_MAP[resource]
    try:
        repo = _get_repo(resource)()
        deleted = getattr(repo, delete_method)(resource_id)
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en admin delete: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)

    if not deleted:
        return JsonResponse({"error": "Recurso no encontrado o ya inactivo."}, status=404)

    return JsonResponse({"success": True, "message": "Recurso eliminado correctamente."}, status=200)
