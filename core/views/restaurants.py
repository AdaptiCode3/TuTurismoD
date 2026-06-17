"""
core/views/restaurants.py
==========================
Vistas DRF para la colección de restaurantes.

Endpoints:
    GET /api/v1/restaurants/            → Lista general (paginada)
    GET /api/v1/restaurants/?lat=&lng=  → Lista ordenada por cercanía ($near)
    GET /api/v1/restaurants/<id>/       → Detalle de un restaurante por ObjectId

RESTRICCIÓN CRÍTICA: Sin django.db.models. Todo a través de RestaurantRepository.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.repositories.restaurants import RestaurantDocument, RestaurantRepository

# Reutilizamos las utilidades de respuesta y validación de places.py
from core.views.places import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    _error,
    _ok,
    _parse_geo_params,
    _parse_pagination,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Serialización
# --------------------------------------------------------------------------- #

def _doc_to_dict(doc: RestaurantDocument) -> dict[str, Any]:
    """Convierte un RestaurantDocument a dict serializable para JSON."""
    return asdict(doc)


# --------------------------------------------------------------------------- #
# Vistas
# --------------------------------------------------------------------------- #

class RestaurantListAPIView(APIView):
    """
    GET /api/v1/restaurants/

    Lista restaurantes. Si se reciben ?lat=&lng=, devuelve resultados
    ordenados por cercanía geográfica ($near). Si no, lista general paginada.

    Query params:
        lat          (float)  — Latitud del punto de referencia.
        lng          (float)  — Longitud del punto de referencia.
        max_distance (int)    — Radio en metros (default 5 000).
        limit        (int)    — Máx resultados (default 20, máx 100).
        skip         (int)    — Offset para paginación (default 0).
        categoria    (str)    — Filtro por tipo de cocina / categoría.
        municipio    (str)    — Filtro por municipio.
    """

    def get(self, request: Request) -> Response:
        lat, lng, max_distance, limit, geo_error = _parse_geo_params(request)
        if geo_error:
            return geo_error

        try:
            repo = RestaurantRepository()
        except RuntimeError as exc:
            logger.critical("MongoDB no disponible en RestaurantListAPIView: %s", exc)
            return _error("Servicio no disponible.", str(exc), status=503)

        # ── Búsqueda por cercanía geoespacial ── #
        if lat is not None and lng is not None:
            restaurants = repo.get_nearby(
                lat=lat,
                lng=lng,
                max_distance=max_distance,
                limit=limit,
            )
            return _ok(
                [_doc_to_dict(r) for r in restaurants],
                count=len(restaurants),
            )

        # ── Lista general con filtros opcionales ── #
        limit, skip, pag_error = _parse_pagination(request)
        if pag_error:
            return pag_error

        categoria = request.query_params.get("categoria", "").strip()
        municipio = request.query_params.get("municipio", "").strip()

        if categoria:
            restaurants = repo.get_by_categoria(categoria)
        elif municipio:
            restaurants = repo.get_by_municipio(municipio)
        else:
            restaurants = repo.get_all(limit=limit, skip=skip, sort_by="nombre")

        return _ok([_doc_to_dict(r) for r in restaurants], count=len(restaurants))


class RestaurantDetailAPIView(APIView):
    """
    GET /api/v1/restaurants/<restaurant_id>/

    Devuelve el detalle de un restaurante por su ObjectId.

    Path params:
        restaurant_id (str) — ObjectId del documento en MongoDB.
    """

    def get(self, request: Request, restaurant_id: str) -> Response:
        try:
            repo = RestaurantRepository()
        except RuntimeError as exc:
            logger.critical("MongoDB no disponible en RestaurantDetailAPIView: %s", exc)
            return _error("Servicio no disponible.", str(exc), status=503)

        restaurant = repo.get_by_id(restaurant_id)
        if restaurant is None:
            return _error(
                "Restaurante no encontrado.",
                f"No existe ningún restaurante con id='{restaurant_id}'.",
                status=404,
            )

        return _ok(_doc_to_dict(restaurant))
