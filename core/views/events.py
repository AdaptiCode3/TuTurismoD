"""
core/views/events.py
=====================
Vistas DRF para la colección de eventos turísticos.

Endpoints:
    GET /api/v1/core/events/          → Lista de eventos (paginada + filtros)
    GET /api/v1/core/events/<id>/     → Detalle de un evento por ObjectId

Filtros disponibles (query params):
    categoria    → Filtra por categoría de evento
    municipio    → Filtra por municipio
    limit        → Máx resultados (default 20, máx 100)
    skip         → Offset para paginación

RESTRICCIÓN: Sin django.db.models. Todo a través de EventRepository + PyMongo.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.repositories.events import EventDocument, EventRepository
from core.views.places import _error, _ok, _parse_pagination

logger = logging.getLogger(__name__)


def _doc_to_dict(doc: EventDocument) -> dict[str, Any]:
    """Convierte un EventDocument a dict serializable para JSON."""
    return asdict(doc)


class EventListAPIView(APIView):
    """
    GET /api/v1/core/events/

    Lista eventos. Admite filtros opcionales por categoría y municipio.

    Query params:
        categoria  (str) — Filtro por categoría (ej. "Festival").
        municipio  (str) — Filtro por municipio.
        limit      (int) — Máx resultados (default 20, máx 100).
        skip       (int) — Offset para paginación (default 0).
    """

    def get(self, request: Request) -> Response:
        limit, skip, pag_error = _parse_pagination(request)
        if pag_error:
            return pag_error

        try:
            repo = EventRepository()
        except RuntimeError as exc:
            logger.critical("MongoDB no disponible en EventListAPIView: %s", exc)
            return _error("Servicio no disponible.", str(exc), status=503)

        categoria = request.query_params.get("categoria", "").strip()
        municipio = request.query_params.get("municipio", "").strip()

        if categoria:
            import re
            events = repo.get_all(
                query={"$or": [
                    {"categoria": {"$regex": re.escape(categoria), "$options": "i"}},
                    {"category":  {"$regex": re.escape(categoria), "$options": "i"}},
                ]}
            )
        elif municipio:
            import re
            events = repo.get_all(
                query={"$or": [
                    {"municipio":   {"$regex": re.escape(municipio), "$options": "i"}},
                    {"municipality":{"$regex": re.escape(municipio), "$options": "i"}},
                ]}
            )
        else:
            events = repo.get_all(limit=limit, skip=skip, sort_by="nombre")

        return _ok([_doc_to_dict(e) for e in events], count=len(events))


class EventDetailAPIView(APIView):
    """
    GET /api/v1/core/events/<event_id>/

    Devuelve el detalle de un evento por su ObjectId.
    """

    def get(self, request: Request, event_id: str) -> Response:
        try:
            repo = EventRepository()
        except RuntimeError as exc:
            logger.critical("MongoDB no disponible en EventDetailAPIView: %s", exc)
            return _error("Servicio no disponible.", str(exc), status=503)

        event = repo.get_by_id(event_id)
        if event is None:
            return _error(
                "Evento no encontrado.",
                f"No existe ningún evento con id='{event_id}'.",
                status=404,
            )

        return _ok(_doc_to_dict(event))
