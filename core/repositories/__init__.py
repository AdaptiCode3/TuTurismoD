"""
core/repositories/__init__.py
==============================
Punto de entrada del paquete repositories.

    from core.repositories import PlaceRepository, PlaceDocument
    from core.repositories import UserRepository, UserDocument
    from core.repositories import RestaurantRepository, RestaurantDocument
"""
from core.repositories.base import BaseRepository
from core.repositories.places import PlaceDocument, PlaceRepository
from core.repositories.restaurants import RestaurantDocument, RestaurantRepository
from core.repositories.users import UserDocument, UserRepository

__all__ = [
    "BaseRepository",
    "PlaceDocument",
    "PlaceRepository",
    "RestaurantDocument",
    "RestaurantRepository",
    "UserDocument",
    "UserRepository",
]
