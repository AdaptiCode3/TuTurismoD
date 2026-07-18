"""
core/views/users.py
===================
Vistas DRF para la gestión administrativa de usuarios en la colección 'users'.
Protegidas con @jwt_required y validación del rol 'admin'.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.repositories.users import UserRepository
from core.security import jwt_required, PasswordService

logger = logging.getLogger(__name__)

ADMIN_ROLE = "admin"


def _check_admin(request: HttpRequest) -> JsonResponse | None:
    payload = getattr(request, "user_payload", {})
    if payload.get("rol") != ADMIN_ROLE:
        return JsonResponse({"success": False, "error": "Acceso denegado.", "detail": "Se requiere rol admin."}, status=403)
    return None


def _parse_body(request: HttpRequest) -> tuple[dict[str, Any], JsonResponse | None]:
    try:
        body = request.body.decode("utf-8").strip()
        if not body:
            return {}, JsonResponse({"success": False, "error": "Body vacío."}, status=400)
        return json.loads(body), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}, JsonResponse({"success": False, "error": "JSON inválido."}, status=400)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
def users_list_create(request: HttpRequest) -> JsonResponse:
    if (err := _check_admin(request)):
        return err

    repo = UserRepository()

    if request.method == "GET":
        try:
            users = repo.get_all()
            # Devolver lista sin password_hash
            data = [u.to_safe_dict() for u in users]
            return JsonResponse({"success": True, "data": data, "count": len(data)}, status=200)
        except RuntimeError as exc:
            logger.critical("MongoDB no disponible en admin get users: %s", exc)
            return JsonResponse({"success": False, "error": "Servicio no disponible."}, status=503)

    # POST - crear usuario desde admin
    data, err = _parse_body(request)
    if err:
        return err

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", "")).strip()
    nombre = str(data.get("nombre", "")).strip()
    rol = str(data.get("rol", "turista")).strip().lower()

    if not email or not password:
        return JsonResponse({"success": False, "error": "Email y contraseña son obligatorios."}, status=400)

    try:
        if repo.email_exists(email):
            return JsonResponse({"success": False, "error": "El correo ya está registrado."}, status=400)

        hashed = PasswordService.hash(password)
        new_id = repo.create_user(
            email=email,
            password_hash=hashed,
            nombre=nombre,
            rol=rol,
            telefono=data.get("telefono")
        )

        if not new_id:
            return JsonResponse({"success": False, "error": "Error al crear usuario."}, status=400)

        user = repo.get_by_id(new_id)
        if not user:
            return JsonResponse({"success": False, "error": "Usuario no encontrado tras crearlo."}, status=500)

        return JsonResponse({"success": True, "data": user.to_safe_dict()}, status=201)
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en admin create user: %s", exc)
        return JsonResponse({"success": False, "error": "Servicio no disponible."}, status=503)


@csrf_exempt
@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@jwt_required
def user_detail(request: HttpRequest, user_id: str) -> JsonResponse:
    if (err := _check_admin(request)):
        return err

    repo = UserRepository()

    try:
        user = repo.get_by_id(user_id)
        if not user:
            return JsonResponse({"success": False, "error": "Usuario no encontrado."}, status=404)

        if request.method == "GET":
            return JsonResponse({"success": True, "data": user.to_safe_dict()}, status=200)

        if request.method in ["PUT", "PATCH"]:
            data, err = _parse_body(request)
            if err:
                return err

            allowed_fields = {"nombre", "rol", "activo", "telefono", "email"}
            updates = {k: v for k, v in data.items() if k in allowed_fields}

            # Si actualizan contraseña
            if "password" in data and str(data["password"]).strip():
                updates["password_hash"] = PasswordService.hash(str(data["password"]).strip())
                updates["password"] = updates["password_hash"]

            if updates:
                repo.update(user_id, updates)
                user = repo.get_by_id(user_id)

            return JsonResponse({"success": True, "data": user.to_safe_dict() if user else {}}, status=200)

        if request.method == "DELETE":
            # Eliminación del usuario
            repo.delete(user_id)
            return JsonResponse({"success": True, "message": "Usuario eliminado correctamente."}, status=200)

    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en admin user detail: %s", exc)
        return JsonResponse({"success": False, "error": "Servicio no disponible."}, status=503)
