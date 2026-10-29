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


def _parse_body(request: HttpRequest) -> tuple[dict[str, Any], Any, JsonResponse | None]:
    """Parsea JSON o multipart (POST/PUT/PATCH). Devuelve (data, files, error).

    Django sólo procesa multipart automáticamente en POST. Para PUT/PATCH se usa
    MultiPartParser manualmente; los archivos se devuelven en lugar de asignarse a
    request.FILES, que es una propiedad de sólo lectura en WSGIRequest.
    """
    from django.http.multipartparser import MultiPartParserError
    from django.utils.datastructures import MultiValueDict

    data: dict[str, Any] = {}
    files: Any = MultiValueDict()
    content_type = getattr(request, "content_type", "") or request.META.get("CONTENT_TYPE", "")
    if "multipart/form-data" in content_type:
        if request.method in ["PUT", "PATCH"]:
            from django.http.multipartparser import MultiPartParser
            try:
                parser = MultiPartParser(request.META, request, request.upload_handlers)
                post, files = parser.parse()
            except MultiPartParserError as exc:
                logger.warning("Multipart inválido en %s: %s", request.method, exc)
                return {}, files, JsonResponse({"error": "Formulario inválido."}, status=400)
            data = post.dict()
        else:
            data = request.POST.dict()
            files = request.FILES
    else:
        try:
            body = request.body.decode("utf-8").strip()
            if not body:
                return {}, files, JsonResponse({"error": "Body vacío."}, status=400)
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}, files, JsonResponse({"error": "JSON inválido."}, status=400)
        if not isinstance(data, dict):
            return {}, files, JsonResponse({"error": "JSON inválido."}, status=400)

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

    return data, files, None


def _sync_existing_image(data: dict[str, Any]) -> None:
    """Si se conserva la imagen actual (imagen_url sin archivo nuevo), replica el valor
    en los campos alternos para que todas las vistas la lean igual."""
    url = str(data.get("imagen_url") or data.get("imagen") or "").strip()
    if url.startswith("http") or url.startswith("data:image/"):
        data["imagen_url"] = url
        data["imagen"] = url
        data["imagenes"] = [url]


_PLACEHOLDER_CLOUD_NAMES = {"", "tuturismo", "your_cloud_name", "demo", "none", "null"}


def _file_to_data_uri(raw_bytes: bytes, content_type: str) -> str:
    """Convierte bytes de imagen en un Data URI base64 persistible en MongoDB."""
    import base64
    mime = content_type if content_type and content_type.startswith("image/") else "image/jpeg"
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _process_image_upload(files: Any, data: dict[str, Any]) -> None:
    """Extrae la imagen de los archivos recibidos y la sube a Cloudinary o la codifica en Data URI."""
    image_file = (
        files.get("imagen")
        or files.get("image")
        or files.get("file")
    ) if files else None
    if not image_file:
        _sync_existing_image(data)
        return

    raw_bytes: bytes = b""
    content_type: str = getattr(image_file, "content_type", "image/jpeg") or "image/jpeg"
    try:
        image_file.seek(0)
        raw_bytes = image_file.read()
    except Exception as read_exc:  # noqa: BLE001
        logger.error("Error leyendo bytes de imagen en admin: %s", read_exc)

    if not raw_bytes:
        _sync_existing_image(data)
        return

    try:
        import os
        cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
        if cloud_name.lower() not in _PLACEHOLDER_CLOUD_NAMES:
            import io
            import cloudinary.uploader
            upload_result = cloudinary.uploader.upload(
                io.BytesIO(raw_bytes),
                folder="tuturismo/recursos",
                resource_type="image",
            )
            secure_url = upload_result.get("secure_url") or upload_result.get("url", "")
            if secure_url:
                data["imagen_url"] = secure_url
                data["imagen"] = secure_url
                data["imagenes"] = [secure_url]
                logger.info("Imagen subida a Cloudinary: %s", secure_url)
                return
    except Exception as img_exc:  # noqa: BLE001
        logger.warning("Cloudinary no disponible (%s); guardando imagen como Data URI.", img_exc)

    # Fallback confiable: almacenar la imagen real subida como Data URI base64 en MongoDB
    data_uri = _file_to_data_uri(raw_bytes, content_type)
    data["imagen_url"] = data_uri
    data["imagen"] = data_uri
    data["imagenes"] = [data_uri]
    logger.info("Imagen almacenada como Data URI (%d bytes).", len(raw_bytes))


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

    # Extraer FILES además de POST
    data, files, err = _parse_body(request)
    if err:
        return err
    if not data:
        return JsonResponse({"error": "Body vacío o sin campos."}, status=400)

    # Procesar y subir imagen (Cloudinary con fallback)
    _process_image_upload(files, data)

    _, _, create_method, _, _ = RESOURCE_MAP[resource]
    try:
        repo = _get_repo(resource)()
        doc = getattr(repo, create_method)(data)
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en admin create: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)

    if doc is None:
        return JsonResponse({"error": "No se pudo crear el recurso."}, status=400)

    # Despachar notificaciones masivas a todos los turistas activos (no bloqueante)
    try:
        payload = getattr(request, "user_payload", {})
        admin_id = str(payload.get("id", ""))
        from core.services.notification_service import dispatch_resource_created
        dispatch_resource_created(resource, doc, admin_id=admin_id)
    except Exception as notif_exc:  # noqa: BLE001
        logger.warning("Notificaciones no enviadas (no crítico): %s", notif_exc)

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

    data, files, err = _parse_body(request)
    if err:
        return err

    # Procesar y subir imagen (Cloudinary con fallback)
    _process_image_upload(files, data)

    _, _, _, update_method, _ = RESOURCE_MAP[resource]
    try:
        repo = _get_repo(resource)()
        doc = getattr(repo, update_method)(resource_id, data)
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en admin update: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error inesperado en admin update [%s/%s]: %s", resource, resource_id, exc)
        return JsonResponse({"error": "No se pudo actualizar el recurso."}, status=500)

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
