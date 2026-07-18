"""core/views/notifications.py — Endpoints para gestión de notificaciones del usuario."""
from __future__ import annotations

import importlib
import json
import logging
from dataclasses import asdict
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.security import jwt_required

logger = logging.getLogger(__name__)


def _get_repo():
    """Resuelve dinámicamente NotificationRepository para facilitar mocks en tests."""
    module = importlib.import_module("core.repositories.notifications")
    return module.NotificationRepository()


def _parse_body(request: HttpRequest) -> tuple[dict[str, Any], JsonResponse | None]:
    try:
        body = request.body.decode("utf-8").strip()
        if not body:
            return {}, JsonResponse({"error": "Body vacío."}, status=400)
        return json.loads(body), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}, JsonResponse({"error": "JSON inválido."}, status=400)


@csrf_exempt
@require_http_methods(["GET", "POST", "DELETE"])
@jwt_required
def notifications_list_create_delete(request: HttpRequest) -> JsonResponse:
    """
    GET    /api/v1/core/notifications/ → Lista notificaciones del usuario
    POST   /api/v1/core/notifications/ → Crea una notificación
    DELETE /api/v1/core/notifications/ → Elimina todas las notificaciones del usuario
    """
    payload = getattr(request, "user_payload", {})
    user_id = str(payload.get("id", ""))
    if not user_id:
        return JsonResponse({"error": "Usuario no autenticado correctamente."}, status=401)

    repo = _get_repo()

    if request.method == "GET":
        items = repo.get_by_user(user_id)
        return JsonResponse({"success": True, "data": [asdict(item) for item in items]}, status=200)

    if request.method == "POST":
        data, err = _parse_body(request)
        if err:
            return err

        titulo = str(data.get("titulo", "")).strip()
        mensaje = str(data.get("mensaje", "")).strip()
        tipo = str(data.get("tipo", "info")).strip()

        if not titulo or not mensaje:
            return JsonResponse({"error": "Los campos 'titulo' y 'mensaje' son requeridos."}, status=400)

        # Si es admin, puede especificar un user_id destino; de lo contrario es para sí mismo
        target_user_id = user_id
        if payload.get("rol") == "admin" and data.get("user_id"):
            target_user_id = str(data.get("user_id")).strip()

        notif = repo.create_notification(target_user_id, titulo, mensaje, tipo)
        if not notif:
            return JsonResponse({"error": "Error al crear notificación."}, status=500)
        return JsonResponse({"success": True, "data": asdict(notif)}, status=201)

    # DELETE all
    count = repo.delete_all_for_user(user_id)
    return JsonResponse({"success": True, "data": {"deleted": count}}, status=200)


@csrf_exempt
@require_http_methods(["PATCH"])
@jwt_required
def notification_mark_all_read(request: HttpRequest) -> JsonResponse:
    """PATCH /api/v1/core/notifications/read-all/ → Marca todas las notificaciones como leídas."""
    payload = getattr(request, "user_payload", {})
    user_id = str(payload.get("id", ""))
    if not user_id:
        return JsonResponse({"error": "Usuario no autenticado correctamente."}, status=401)

    repo = _get_repo()
    modified = repo.mark_all_as_read(user_id)
    return JsonResponse({"success": True, "data": {"modified": modified}}, status=200)


@csrf_exempt
@require_http_methods(["PATCH"])
@jwt_required
def notification_mark_read(request: HttpRequest, notification_id: str) -> JsonResponse:
    """PATCH /api/v1/core/notifications/<notification_id>/read/ → Marca una notificación como leída."""
    payload = getattr(request, "user_payload", {})
    user_id = str(payload.get("id", ""))
    if not user_id:
        return JsonResponse({"error": "Usuario no autenticado correctamente."}, status=401)

    repo = _get_repo()
    notif = repo.mark_as_read(user_id, notification_id)
    if not notif:
        return JsonResponse({"error": "Notificación no encontrada."}, status=404)
    return JsonResponse({"success": True, "data": asdict(notif)}, status=200)


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
def notification_detail(request: HttpRequest, notification_id: str) -> JsonResponse:
    """DELETE /api/v1/core/notifications/<notification_id>/ → Elimina una notificación."""
    payload = getattr(request, "user_payload", {})
    user_id = str(payload.get("id", ""))
    if not user_id:
        return JsonResponse({"error": "Usuario no autenticado correctamente."}, status=401)

    repo = _get_repo()
    deleted = repo.delete_for_user(user_id, notification_id)
    if not deleted:
        return JsonResponse({"error": "Notificación no encontrada."}, status=404)
    return JsonResponse({"success": True, "data": {"deleted": True, "id": notification_id}}, status=200)
