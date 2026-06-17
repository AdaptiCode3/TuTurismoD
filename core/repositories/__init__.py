"""
core/repositories/__init__.py
==============================
Punto de entrada del paquete repositories.

Exporta las clases públicas para un import limpio desde otras capas:

    from core.repositories import PlaceRepository, PlaceDocument
"""
from core.repositories.base import BaseRepository
from core.repositories.places import PlaceDocument, PlaceRepository

__all__ = [
    "BaseRepository",
    "PlaceDocument",
    "PlaceRepository",
]
