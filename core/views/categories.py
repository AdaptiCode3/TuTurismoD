"""
core/views/categories.py
========================
Vistas DRF para la colección de categorías.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.repositories.categories import CategoryDocument, CategoryRepository
from core.views.places import _error, _ok

logger = logging.getLogger(__name__)

def _doc_to_dict(doc: CategoryDocument) -> dict[str, Any]:
    return asdict(doc)

class CategoryListAPIView(APIView):
    """
    GET /api/v1/core/categorias/
    Devuelve la lista de categorías (desde la colección "categorias").
    """
    def get(self, request: Request) -> Response:
        try:
            repo = CategoryRepository()
            categorias = repo.get_all(sort_by="nombre")
            return _ok([_doc_to_dict(c) for c in categorias], count=len(categorias))
        except RuntimeError as exc:
            logger.critical("MongoDB no disponible en CategoryListAPIView: %s", exc)
            return _error("Servicio no disponible.", str(exc), status=503)
