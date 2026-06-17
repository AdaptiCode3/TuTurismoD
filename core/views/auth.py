"""
core/views/auth.py
==================
Endpoints de autenticación JWT para el proyecto Tu-Turismo.

RESTRICCIÓN CRÍTICA: Este módulo NO importa ni usa
  django.contrib.auth, django.db.models ni ningún ORM relacional.
  Toda la autenticación opera sobre la colección 'usuarios' de MongoDB
  mediante UserRepository y PyMongo nativo.

Endpoints implementados:
  POST /api/v1/auth/login/   → Genera token JWT con credenciales válidas.
  POST /api/v1/auth/refresh/ → Intercambia refresh token por nuevo access token.
  GET  /api/v1/auth/me/      → Devuelve el perfil del usuario autenticado.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.repositories.users import UserRepository
from core.security import JWTService, PasswordService, jwt_required

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Helpers internos
# --------------------------------------------------------------------------- #

def _parse_json_body(request: HttpRequest) -> tuple[dict[str, Any], JsonResponse | None]:
    """
    Parsea el body JSON de una request de forma segura.

    Returns:
        (data_dict, None)        si el parsing fue exitoso.
        ({},        error_response) si el body está vacío o malformado.
    """
    try:
        body: str = request.body.decode("utf-8").strip()
        if not body:
            return {}, JsonResponse(
                {"error": "Body vacío.", "detail": "La petición debe incluir un body JSON."},
                status=400,
            )
        return json.loads(body), None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Body JSON malformado: %s", exc)
        return {}, JsonResponse(
            {"error": "JSON inválido.", "detail": "El body de la petición no es JSON válido."},
            status=400,
        )


# --------------------------------------------------------------------------- #
# POST /api/v1/auth/login/
# --------------------------------------------------------------------------- #

@csrf_exempt
@require_http_methods(["POST"])
def login(request: HttpRequest) -> JsonResponse:
    """
    Autentica a un usuario con email y contraseña, devuelve tokens JWT.

    Request body (JSON):
        {
            "email":    "turista@jalisco.mx",
            "password": "mi_contraseña_segura"
        }

    Responses:
        200 OK:
            {
                "access_token":  "<jwt_access_token>",
                "refresh_token": "<jwt_refresh_token>",
                "token_type":    "Bearer",
                "expires_in":    86400,
                "user": {
                    "id":    "<object_id>",
                    "email": "turista@jalisco.mx",
                    "rol":   "turista",
                    "nombre": "..."
                }
            }
        400 Bad Request  → Campos faltantes o formato inválido.
        401 Unauthorized → Credenciales incorrectas.
        503 Unavailable  → MongoDB no disponible.
    """
    # ── 1. Parsear body ─────────────────────────────────────────────────── #
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    email: str = str(data.get("email", "")).strip().lower()
    password: str = str(data.get("password", "")).strip()

    # ── 2. Validar campos obligatorios ───────────────────────────────────── #
    missing: list[str] = []
    if not email:
        missing.append("email")
    if not password:
        missing.append("password")

    if missing:
        return JsonResponse(
            {
                "error": "Campos obligatorios faltantes.",
                "detail": f"Los siguientes campos son requeridos: {missing}",
            },
            status=400,
        )

    # ── 3. Buscar usuario en MongoDB ─────────────────────────────────────── #
    try:
        repo = UserRepository()
        user = repo.get_user_by_email(email)
    except RuntimeError as exc:
        # MongoDBClient.get_database() lanza RuntimeError si el cluster no responde
        logger.critical("MongoDB no disponible en login: %s", exc)
        return JsonResponse(
            {
                "error": "Servicio no disponible.",
                "detail": "La base de datos no está accesible en este momento.",
            },
            status=503,
        )

    # ── 4. Verificar existencia del usuario ──────────────────────────────── #
    # IMPORTANTE: El mensaje de error es genérico a propósito para no revelar
    # si el email existe en la base de datos (previene email enumeration attacks).
    if user is None:
        logger.warning("Intento de login fallido: usuario no encontrado para email='%s'", email)
        return JsonResponse(
            {
                "error": "Credenciales inválidas.",
                "detail": "El email o la contraseña son incorrectos.",
            },
            status=401,
        )

    # ── 5. Verificar contraseña (hash bcrypt) ────────────────────────────── #
    # user.password_hash contiene el valor del campo 'password' de MongoDB
    if not PasswordService.verify(password, user.password_hash):
        logger.warning(
            "Intento de login fallido: contraseña incorrecta para user_id='%s'", user.id
        )
        return JsonResponse(
            {
                "error": "Credenciales inválidas.",
                "detail": "El email o la contraseña son incorrectos.",
            },
            status=401,
        )

    # ── 6. Verificar que la cuenta está activa ───────────────────────────── #
    if not user.activo:
        logger.warning("Login bloqueado: cuenta inactiva para user_id='%s'", user.id)
        return JsonResponse(
            {
                "error": "Cuenta desactivada.",
                "detail": "Tu cuenta ha sido desactivada. Contacta al administrador.",
            },
            status=401,
        )

    # ── 7. Generar tokens JWT ────────────────────────────────────────────── #
    # El payload incluye SÓLO los datos mínimos necesarios para autorización.
    # ObjectId ya viene convertido a string desde UserDocument.id
    token_payload: dict[str, Any] = {
        "id":    user.id,       # str(ObjectId) — serializable en JWT
        "email": user.email,
        "rol":   user.rol,      # 'admin' | 'turista'
    }

    access_token: str  = JWTService.encode(token_payload)
    refresh_token: str = JWTService.encode_refresh(user.id)  # type: ignore[arg-type]

    # ── 8. Actualizar last_login (fire-and-forget) ────────────────────────── #
    try:
        repo.update_last_login(user.id)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        # No debe interrumpir el login si falla la auditoría
        logger.warning("No se pudo actualizar last_login para user_id='%s': %s", user.id, exc)

    # ── 9. Respuesta exitosa ─────────────────────────────────────────────── #
    logger.info("Login exitoso: user_id='%s', rol='%s'", user.id, user.rol)

    return JsonResponse(
        {
            "access_token":  access_token,
            "refresh_token": refresh_token,
            "token_type":    "Bearer",
            "expires_in":    86_400,    # 24 horas en segundos
            "user": {
                "id":     user.id,
                "email":  user.email,
                "rol":    user.rol,
                "nombre": user.nombre,
            },
        },
        status=200,
    )


# --------------------------------------------------------------------------- #
# POST /api/v1/auth/refresh/
# --------------------------------------------------------------------------- #

@csrf_exempt
@require_http_methods(["POST"])
def refresh_token(request: HttpRequest) -> JsonResponse:
    """
    Intercambia un refresh token válido por un nuevo access token.

    Request body (JSON):
        { "refresh_token": "<jwt_refresh_token>" }

    Responses:
        200 OK  → { "access_token": "...", "token_type": "Bearer", "expires_in": 86400 }
        400     → Campo faltante.
        401     → Refresh token inválido, expirado o de tipo incorrecto.
    """
    data, error_response = _parse_json_body(request)
    if error_response:
        return error_response

    raw_refresh: str = str(data.get("refresh_token", "")).strip()
    if not raw_refresh:
        return JsonResponse(
            {"error": "Campo requerido.", "detail": "El campo 'refresh_token' es obligatorio."},
            status=400,
        )

    payload = JWTService.decode(raw_refresh)

    # Verificar que es un refresh token (no un access token reutilizado)
    if payload is None or payload.get("type") != "refresh":
        return JsonResponse(
            {
                "error": "Refresh token inválido o expirado.",
                "detail": "Proporciona un refresh token válido para obtener un nuevo acceso.",
            },
            status=401,
        )

    user_id: str = payload.get("id", "")

    # Recuperar datos frescos del usuario desde MongoDB
    try:
        repo = UserRepository()
        user = repo.get_by_id(user_id)
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en refresh: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)

    if user is None or not user.activo:
        return JsonResponse(
            {"error": "Usuario no encontrado o inactivo.", "detail": "No se puede renovar el token."},
            status=401,
        )

    # Generar nuevo access token con datos actualizados (por si cambió el rol)
    new_access: str = JWTService.encode({
        "id":    user.id,
        "email": user.email,
        "rol":   user.rol,
    })

    logger.info("Token renovado para user_id='%s'", user_id)

    return JsonResponse(
        {
            "access_token": new_access,
            "token_type":   "Bearer",
            "expires_in":   86_400,
        },
        status=200,
    )


# --------------------------------------------------------------------------- #
# GET /api/v1/auth/me/
# --------------------------------------------------------------------------- #

@jwt_required
def me(request: HttpRequest) -> JsonResponse:
    """
    Devuelve el perfil del usuario actualmente autenticado.

    Requiere header: Authorization: Bearer <access_token>

    Responses:
        200 OK  → Datos del usuario (sin password).
        401     → Token ausente, inválido o expirado (manejado por @jwt_required).
    """
    # request.user_payload fue inyectado por @jwt_required
    payload: dict[str, Any] = request.user_payload  # type: ignore[attr-defined]
    user_id: str = payload.get("id", "")

    try:
        repo = UserRepository()
        user = repo.get_by_id(user_id)
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en /me: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)

    if user is None:
        return JsonResponse(
            {"error": "Usuario no encontrado.", "detail": "El token es válido pero el usuario ya no existe."},
            status=404,
        )

    return JsonResponse(user.to_safe_dict(), status=200)
