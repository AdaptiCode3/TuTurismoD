"""
core/views/password_recovery.py
=================================
Servicio de recuperación de contraseña por correo electrónico con código de 6 dígitos.
Incluye envío por email (send_mail) y fallback en consola de logs.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Any

from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.database import MongoDBClient
from core.repositories.users import UserRepository
from core.security import PasswordService

logger = logging.getLogger(__name__)


def _parse_body(request: HttpRequest) -> tuple[dict[str, Any], JsonResponse | None]:
    try:
        body = request.body.decode("utf-8").strip()
        if not body:
            return {}, JsonResponse({"success": False, "message": "Body vacío."}, status=400)
        return json.loads(body), None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}, JsonResponse({"success": False, "message": "JSON inválido."}, status=400)


def _get_recovery_collection():
    db = MongoDBClient.get_database()
    return db["password_resets"]


@csrf_exempt
@require_http_methods(["POST"])
def send_recovery_code(request: HttpRequest) -> JsonResponse:
    """
    POST /api/v1/auth/password/send-code/
    POST /api/v1/core/auth/password/send-code/
    Envía un código de 6 dígitos al correo electrónico registrado.
    """
    data, err = _parse_body(request)
    if err:
        return err

    email = str(data.get("email", "")).strip().lower()
    if not email:
        return JsonResponse({"success": False, "message": "Por favor ingresa un correo electrónico."}, status=400)

    try:
        user_repo = UserRepository()
        user = user_repo.get_by_email(email)
        if not user:
            # Por seguridad o feedback, si el usuario no existe podemos indicarlo o retornar 404
            return JsonResponse({"success": False, "message": "No existe una cuenta registrada con este correo electrónico."}, status=404)

        code = f"{random.randint(100000, 999999)}"
        now = datetime.now(tz=timezone.utc)
        expires_at = now + timedelta(minutes=15)

        col = _get_recovery_collection()
        # Invalidar códigos anteriores de este correo
        col.update_many({"email": email, "used": False}, {"$set": {"used": True}})

        col.insert_one({
            "email": email,
            "code": code,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "used": False,
        })

        # Log en consola (Fallback e indispensable para testing en entorno local)
        logger.info("=" * 60)
        logger.info(f"🔑 CÓDIGO DE RECUPERACIÓN PARA {email}: [{code}]")
        logger.info("=" * 60)

        # Intentar envío de correo mediante SMTP o backend configurado en Django
        try:
            subject = "Código de recuperación de contraseña - Tu-Turismo"
            message = f"Hola {user.nombre or 'Turista'},\n\nTu código de verificación para restablecer tu contraseña es: {code}\n\nEste código expira en 15 minutos.\nSi no solicitaste esto, puedes ignorar este correo.\n\nSaludos,\nEl equipo de Tu-Turismo"
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "Tu-Turismo <onboarding@resend.dev>")
            send_mail(subject, message, from_email, [email], fail_silently=False)
            logger.info(f"✉️ Correo de recuperación enviado con éxito a {email}")
        except Exception as mail_exc:
            logger.warning(f"⚠️ No se pudo enviar correo por SMTP a {email}: {mail_exc}. El código está disponible en consola arriba.")

        return JsonResponse({"success": True, "message": "Código enviado correctamente. Revisa tu correo o consola de logs."}, status=200)

    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en send_recovery_code: %s", exc)
        return JsonResponse({"success": False, "message": "Servicio de base de datos no disponible."}, status=503)
    except Exception as exc:
        logger.error("Error inesperado en send_recovery_code: %s", exc)
        return JsonResponse({"success": False, "message": "Ocurrió un error al procesar la solicitud."}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def verify_recovery_code(request: HttpRequest) -> JsonResponse:
    """
    POST /api/v1/auth/password/verify-code/
    POST /api/v1/core/auth/password/verify-code/
    Verifica que el código de 6 dígitos sea correcto y no haya expirado.
    """
    data, err = _parse_body(request)
    if err:
        return err

    email = str(data.get("email", "")).strip().lower()
    code = str(data.get("code", "")).strip()

    if not email or not code:
        return JsonResponse({"success": False, "message": "Email y código son requeridos."}, status=400)

    try:
        col = _get_recovery_collection()
        doc = col.find_one({"email": email, "code": code, "used": False}, sort=[("_id", -1)])

        if not doc:
            return JsonResponse({"success": False, "message": "El código es incorrecto o ya fue utilizado."}, status=400)

        expires_at_str = doc.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now(tz=timezone.utc) > expires_at:
                    return JsonResponse({"success": False, "message": "El código ha expirado. Solicita uno nuevo."}, status=400)
            except ValueError:
                pass

        return JsonResponse({"success": True, "message": "Código verificado correctamente."}, status=200)

    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en verify_recovery_code: %s", exc)
        return JsonResponse({"success": False, "message": "Servicio de base de datos no disponible."}, status=503)


@csrf_exempt
@require_http_methods(["POST"])
def reset_password(request: HttpRequest) -> JsonResponse:
    """
    POST /api/v1/auth/password/reset/
    POST /api/v1/core/auth/password/reset/
    Restablece la contraseña una vez validado el código.
    """
    data, err = _parse_body(request)
    if err:
        return err

    email = str(data.get("email", "")).strip().lower()
    code = str(data.get("code", "")).strip()
    password = str(data.get("password", "")).strip()

    if not email or not code or not password:
        return JsonResponse({"success": False, "message": "Todos los campos son obligatorios."}, status=400)

    if len(password) < 8:
        return JsonResponse({"success": False, "message": "La contraseña debe tener al menos 8 caracteres."}, status=400)

    try:
        col = _get_recovery_collection()
        doc = col.find_one({"email": email, "code": code, "used": False}, sort=[("_id", -1)])

        if not doc:
            return JsonResponse({"success": False, "message": "El código es incorrecto o ya fue utilizado."}, status=400)

        expires_at_str = doc.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now(tz=timezone.utc) > expires_at:
                    return JsonResponse({"success": False, "message": "El código ha expirado. Solicita uno nuevo."}, status=400)
            except ValueError:
                pass

        user_repo = UserRepository()
        user = user_repo.get_by_email(email)
        if not user:
            return JsonResponse({"success": False, "message": "No existe una cuenta registrada con este correo electrónico."}, status=404)

        hashed = PasswordService.hash(password)
        # Actualizar contraseña del usuario en MongoDB
        updated = user_repo.update(user.id, {"password": hashed, "password_hash": hashed})
        if not updated:
            return JsonResponse({"success": False, "message": "No se pudo actualizar la contraseña en la base de datos."}, status=500)

        # Marcar código como usado
        col.update_one({"_id": doc["_id"]}, {"$set": {"used": True}})

        return JsonResponse({"success": True, "message": "Contraseña restablecida exitosamente."}, status=200)

    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en reset_password: %s", exc)
        return JsonResponse({"success": False, "message": "Servicio de base de datos no disponible."}, status=503)
