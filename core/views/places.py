"""
core/views/places.py
=====================
Vistas DRF para la colección de lugares turísticos.

Endpoints:
    GET /api/v1/places/              → Lista general (paginada)
    GET /api/v1/places/?lat=&lng=    → Lista ordenada por cercanía ($near)
    GET /api/v1/places/<id>/         → Detalle de un lugar por ObjectId
    GET /api/v1/places/categorias/   → Lista de categorías únicas
    GET /api/v1/places/municipios/   → Lista de municipios únicos

RESTRICCIÓN CRÍTICA: Sin django.db.models. Todo a través de PlaceRepository.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.repositories.places import PlaceDocument, PlaceRepository
from core.security import jwt_required

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Paginación por defecto
# --------------------------------------------------------------------------- #
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


# --------------------------------------------------------------------------- #
# Utilidades de serialización y respuesta uniforme
# --------------------------------------------------------------------------- #

def _doc_to_dict(doc: PlaceDocument) -> dict[str, Any]:
    """
    Convierte un PlaceDocument a dict serializable para JSON.

    El ObjectId ya viene como string (gestionado por BaseRepository),
    por lo que no requiere conversión adicional aquí.
    """
    return asdict(doc)


def _ok(data: Any, *, count: int | None = None, status: int = 200) -> Response:
    """Respuesta de éxito con estructura uniforme."""
    body: dict[str, Any] = {"success": True, "data": data}
    if count is not None:
        body["count"] = count
    return Response(body, status=status)


def _error(message: str, detail: str = "", *, status: int = 400) -> Response:
    """Respuesta de error con estructura uniforme."""
    body: dict[str, Any] = {"success": False, "error": message}
    if detail:
        body["detail"] = detail
    return Response(body, status=status)


def _parse_geo_params(
    request: Request,
) -> tuple[float | None, float | None, int, int, Response | None]:
    """
    Extrae y valida los parámetros geoespaciales y de paginación del query string.

    Parámetros aceptados:
        lat          : Latitud decimal (float)
        lng          : Longitud decimal (float)
        max_distance : Radio en metros (int, default 10000)
        limit        : Máx resultados (int, default DEFAULT_LIMIT)

    Returns:
        (lat, lng, max_distance, limit, error_response)
        Si hay error de validación, error_response es un Response 400.
    """
    raw_lat = request.query_params.get("lat")
    raw_lng = request.query_params.get("lng")
    raw_max_dist = request.query_params.get("max_distance", "10000")
    raw_limit = request.query_params.get("limit", str(DEFAULT_LIMIT))

    lat: float | None = None
    lng: float | None = None

    if raw_lat is not None or raw_lng is not None:
        # Ambos son obligatorios si uno se proporciona
        if raw_lat is None or raw_lng is None:
            return None, None, 0, 0, _error(
                "Parámetros incompletos.",
                "Si envías 'lat' debes enviar también 'lng' y viceversa.",
            )
        try:
            lat = float(raw_lat)
            lng = float(raw_lng)
        except ValueError:
            return None, None, 0, 0, _error(
                "Parámetros geográficos inválidos.",
                f"'lat' y 'lng' deben ser números decimales. "
                f"Recibido: lat='{raw_lat}', lng='{raw_lng}'.",
            )

        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return None, None, 0, 0, _error(
                "Coordenadas fuera de rango.",
                "lat debe estar entre -90 y 90; lng entre -180 y 180.",
            )

    try:
        max_distance = int(raw_max_dist)
        limit = min(int(raw_limit), MAX_LIMIT)
    except ValueError:
        return None, None, 0, 0, _error(
            "Parámetros de paginación inválidos.",
            "'limit' y 'max_distance' deben ser enteros.",
        )

    return lat, lng, max_distance, limit, None


def _parse_pagination(request: Request) -> tuple[int, int, Response | None]:
    """Extrae y valida 'limit' y 'skip' del query string."""
    raw_limit = request.query_params.get("limit", str(DEFAULT_LIMIT))
    raw_skip  = request.query_params.get("skip", "0")
    try:
        limit = min(int(raw_limit), MAX_LIMIT)
        skip  = max(int(raw_skip), 0)
        return limit, skip, None
    except ValueError:
        return 0, 0, _error(
            "Parámetros de paginación inválidos.",
            "'limit' y 'skip' deben ser enteros.",
        )


# --------------------------------------------------------------------------- #
# Vistas
# --------------------------------------------------------------------------- #

class PlaceListAPIView(APIView):
    """
    GET /api/v1/places/

    Lista lugares turísticos. Si se reciben ?lat=&lng=, devuelve resultados
    ordenados por cercanía geográfica ($near). Si no, lista general paginada.

    Query params:
        lat          (float)  — Latitud del punto de referencia.
        lng          (float)  — Longitud del punto de referencia.
        max_distance (int)    — Radio en metros (default 10 000).
        limit        (int)    — Máx resultados (default 20, máx 100).
        skip         (int)    — Offset para paginación (default 0).
        categoria    (str)    — Filtro por categoría.
        municipio    (str)    — Filtro por municipio.
    """

    def get(self, request: Request) -> Response:
        lat, lng, max_distance, limit, geo_error = _parse_geo_params(request)
        if geo_error:
            return geo_error

        try:
            repo = PlaceRepository()
        except RuntimeError as exc:
            logger.critical("MongoDB no disponible en PlaceListAPIView: %s", exc)
            return _error("Servicio no disponible.", str(exc), status=503)

        # ── Búsqueda por cercanía geoespacial ── #
        if lat is not None and lng is not None:
            places = repo.get_nearby(lat=lat, lng=lng, max_distance=max_distance, limit=limit)
            return _ok(
                [_doc_to_dict(p) for p in places],
                count=len(places),
            )

        # ── Lista general con filtros opcionales ── #
        limit, skip, pag_error = _parse_pagination(request)
        if pag_error:
            return pag_error

        categoria = request.query_params.get("categoria", "").strip()
        municipio = request.query_params.get("municipio", "").strip()

        if categoria:
            places = repo.get_by_categoria(categoria)
        elif municipio:
            places = repo.get_by_municipio(municipio)
        else:
            places = repo.get_all(limit=limit, skip=skip, sort_by="nombre")

        return _ok([_doc_to_dict(p) for p in places], count=len(places))


class PlaceDetailAPIView(APIView):
    """
    GET /api/v1/places/<place_id>/

    Devuelve el detalle de un lugar turístico por su ObjectId.

    Path params:
        place_id (str) — ObjectId del documento en MongoDB.
    """

    def get(self, request: Request, place_id: str) -> Response:
        try:
            repo = PlaceRepository()
        except RuntimeError as exc:
            logger.critical("MongoDB no disponible en PlaceDetailAPIView: %s", exc)
            return _error("Servicio no disponible.", str(exc), status=503)

        place = repo.get_by_id(place_id)
        if place is None:
            return _error(
                "Lugar no encontrado.",
                f"No existe ningún lugar con id='{place_id}'.",
                status=404,
            )

        return _ok(_doc_to_dict(place))


class PlaceCategoriasAPIView(APIView):
    """
    GET /api/v1/places/categorias/

    Devuelve la lista de categorías únicas disponibles en la colección.
    """

    def get(self, request: Request) -> Response:
        try:
            repo = PlaceRepository()
            categorias = repo.get_categorias_disponibles()
        except RuntimeError as exc:
            return _error("Servicio no disponible.", str(exc), status=503)

        return _ok(categorias, count=len(categorias))


class PlaceMunicipiosAPIView(APIView):
    """
    GET /api/v1/places/municipios/

    Devuelve la lista de municipios únicos disponibles en la colección.
    """

    def get(self, request: Request) -> Response:
        try:
            repo = PlaceRepository()
            municipios = repo.get_municipios_disponibles()
        except RuntimeError as exc:
            return _error("Servicio no disponible.", str(exc), status=503)

        return _ok(municipios, count=len(municipios))
