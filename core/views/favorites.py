"""
core/views/favorites.py
========================
Endpoints del módulo de Favoritos para el proyecto Tu-Turismo.

RESTRICCIÓN CRÍTICA: Este módulo NO importa ni usa
  django.contrib.auth, django.db.models ni ningún ORM relacional.

Endpoints implementados:
  GET    /api/v1/core/favorites/               → Lista los favoritos del usuario autenticado.
  POST   /api/v1/core/favorites/               → Agrega un recurso a favoritos.
  DELETE /api/v1/core/favorites/<referencia_id>/ → Elimina un favorito por ID de recurso.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from core.repositories.favorites import FavoriteRepository, VALID_TIPOS, normalize_tipo
from core.security import jwt_required

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Helpers internos
# --------------------------------------------------------------------------- #

def _parse_json_body(request: HttpRequest) -> tuple[dict[str, Any], JsonResponse | None]:
    """Parsea el body JSON de una request de forma segura."""
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
# GET / POST  /api/v1/core/favorites/
# --------------------------------------------------------------------------- #

@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
def favorites_list_create(request: HttpRequest) -> JsonResponse:
    """
    GET  → Devuelve la lista de favoritos del usuario autenticado.
           Acepta el parámetro de query ?tipo=lugar|restaurante|evento para filtrar.
    POST → Agrega un recurso a los favoritos.
           Body: { "tipo": "lugar", "referencia_id": "<objectid>" }

    Responses:
        200 GET  → { "success": true, "data": [...], "count": N }
        201 POST → { "success": true, "data": { favorito }, "message": "..." }
        400      → Validación fallida (tipo inválido, faltante, duplicado).
        503      → MongoDB no disponible.
    """
    payload: dict[str, Any] = request.user_payload  # type: ignore[attr-defined]
    user_id: str = payload.get("id", "")

    try:
        repo = FavoriteRepository()

        # ── GET: Listar favoritos ─────────────────────────────────────── #
        if request.method == "GET":
            tipo_filter = request.GET.get("tipo", "").strip().lower()

            if tipo_filter and (tipo_filter in VALID_TIPOS or normalize_tipo(tipo_filter) in ("lugar", "restaurante", "evento")):
                favorites = repo.get_by_user_and_tipo(user_id, tipo_filter)
            else:
                favorites = repo.get_by_user(user_id)

            return JsonResponse(
                {
                    "success": True,
                    "data": [asdict(fav) for fav in favorites],
                    "count": len(favorites),
                },
                status=200,
            )

        # ── POST: Agregar favorito ────────────────────────────────────── #
        data, error_response = _parse_json_body(request)
        if error_response:
            return error_response

        tipo: str = str(data.get("tipo", "")).strip().lower()
        referencia_id: str = str(data.get("referencia_id", "")).strip()

        # Validaciones
        if not tipo:
            return JsonResponse(
                {"error": "Campo 'tipo' requerido.", "detail": f"Debe ser uno de: {sorted(VALID_TIPOS)}"},
                status=400,
            )
        norm_tipo = normalize_tipo(tipo)
        if tipo not in VALID_TIPOS and norm_tipo not in ("lugar", "restaurante", "evento"):
            return JsonResponse(
                {"error": "Tipo de recurso inválido.", "detail": f"Los tipos válidos son: {sorted(VALID_TIPOS)}"},
                status=400,
            )
        if not referencia_id:
            return JsonResponse(
                {"error": "Campo 'referencia_id' requerido.", "detail": "Proporciona el ID del recurso a guardar."},
                status=400,
            )

        # Verificar si ya existe (409 Conflict)
        if repo.already_saved(user_id, referencia_id):
            # Devolver 200 idempotente en lugar de error — el frontend lo trata igual
            return JsonResponse(
                {
                    "success": True,
                    "message": "El recurso ya estaba en tus favoritos.",
                    "already_exists": True,
                },
                status=200,
            )

        favorite = repo.add_favorite(user_id=user_id, tipo=norm_tipo, referencia_id=referencia_id)
        if favorite is None:
            return JsonResponse(
                {"error": "No se pudo agregar el favorito.", "detail": "Error interno al insertar en MongoDB."},
                status=400,
            )

        return JsonResponse(
            {
                "success": True,
                "data": asdict(favorite),
                "message": "Recurso agregado a favoritos correctamente.",
            },
            status=201,
        )

    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en /favorites/: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)


# --------------------------------------------------------------------------- #
# DELETE /api/v1/core/favorites/<referencia_id>/
# --------------------------------------------------------------------------- #

@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
def favorites_delete(request: HttpRequest, referencia_id: str) -> JsonResponse:
    """
    Elimina un favorito del usuario autenticado.

    Args (URL):
        referencia_id: ObjectId del recurso a eliminar de favoritos.

    Responses:
        200 → { "success": true, "message": "..." }
        404 → El favorito no existe para este usuario.
        503 → MongoDB no disponible.
    """
    payload: dict[str, Any] = request.user_payload  # type: ignore[attr-defined]
    user_id: str = payload.get("id", "")

    referencia_id = referencia_id.strip()
    if not referencia_id:
        return JsonResponse(
            {"error": "referencia_id es requerido.", "detail": "Incluye el ID del recurso en la URL."},
            status=400,
        )

    try:
        repo = FavoriteRepository()
        deleted = repo.remove_favorite(user_id=user_id, referencia_id=referencia_id)
    except RuntimeError as exc:
        logger.critical("MongoDB no disponible en DELETE /favorites/: %s", exc)
        return JsonResponse({"error": "Servicio no disponible."}, status=503)

    if not deleted:
        return JsonResponse(
            {
                "success": False,
                "error": "Favorito no encontrado.",
                "detail": "El recurso no está en tu lista de favoritos.",
            },
            status=404,
        )

    return JsonResponse(
        {
            "success": True,
            "message": "Favorito eliminado correctamente.",
        },
        status=200,
    )
