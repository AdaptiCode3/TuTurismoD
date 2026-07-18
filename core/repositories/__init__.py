"""
core/repositories/__init__.py
==============================
Punto de entrada del paquete repositories.

    from core.repositories import PlaceRepository, PlaceDocument
    from core.repositories import UserRepository, UserDocument
    from core.repositories import RestaurantRepository, RestaurantDocument
    from core.repositories import FavoriteRepository, FavoriteDocument
"""
from core.repositories.base import BaseRepository
from core.repositories.favorites import FavoriteDocument, FavoriteRepository
from core.repositories.notifications import NotificationDocument, NotificationRepository
from core.repositories.places import PlaceDocument, PlaceRepository
from core.repositories.restaurants import RestaurantDocument, RestaurantRepository
from core.repositories.users import UserDocument, UserRepository

__all__ = [
    "BaseRepository",
    "FavoriteDocument",
    "FavoriteRepository",
    "NotificationDocument",
    "NotificationRepository",
    "PlaceDocument",
    "PlaceRepository",
    "RestaurantDocument",
    "RestaurantRepository",
    "UserDocument",
    "UserRepository",
]
