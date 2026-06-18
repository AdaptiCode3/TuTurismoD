"""
core/urls.py
============
Rutas de la aplicación core.

Estructura:
  /api/v1/core/health/          → Health-check del sistema
  /api/v1/core/auth/login/      → Login JWT
  /api/v1/core/auth/refresh/    → Renovar access token
  /api/v1/core/auth/me/         → Perfil del usuario autenticado

  /api/v1/places/               → Lista de lugares (+ ?lat&lng para geo)
  /api/v1/places/categorias/    → Categorías únicas
  /api/v1/places/municipios/    → Municipios únicos
  /api/v1/places/<id>/          → Detalle de un lugar

  /api/v1/core/events/           → Lista de eventos
  /api/v1/core/events/<id>/     → Detalle de un evento

  /api/v1/restaurants/          → Lista de restaurantes (+ ?lat&lng para geo)
  /api/v1/restaurants/<id>/     → Detalle de un restaurante

NOTA: Las rutas de lugares y restaurantes viven en el URLconf raíz
(tuturismo_backend/urls.py) con prefijo /api/v1/. Las rutas de core
usan el prefijo /api/v1/core/.
"""
from django.urls import path

from core.views import health_check
from core.views.auth import login, me, refresh_token
from core.views.places import (
    PlaceCategoriasAPIView,
    PlaceDetailAPIView,
    PlaceListAPIView,
    PlaceMunicipiosAPIView,
)
from core.views.restaurants import (
    RestaurantDetailAPIView,
    RestaurantListAPIView,
)
from core.views.categories import CategoryListAPIView
from core.views.events import EventDetailAPIView, EventListAPIView

app_name = "core"

urlpatterns = [
    # ── Sistema ───────────────────────────────────────────────────────── #
    # GET /api/v1/core/health/
    path("health/", health_check, name="health_check"),

    # ── Autenticación JWT ─────────────────────────────────────────────── #
    # POST /api/v1/core/auth/login/
    path("auth/login/",   login,         name="auth_login"),
    # POST /api/v1/core/auth/refresh/
    path("auth/refresh/", refresh_token, name="auth_refresh"),
    # GET  /api/v1/core/auth/me/
    path("auth/me/",      me,            name="auth_me"),

    # ── Lugares turísticos ────────────────────────────────────────────── #
    # GET /api/v1/core/places/
    # GET /api/v1/core/places/?lat=20.67&lng=-103.34&max_distance=5000
    path("places/",                    PlaceListAPIView.as_view(),       name="place_list"),
    # GET /api/v1/core/places/categorias/
    path("places/categorias/",         PlaceCategoriasAPIView.as_view(), name="place_categorias"),
    # GET /api/v1/core/places/municipios/
    path("places/municipios/",         PlaceMunicipiosAPIView.as_view(), name="place_municipios"),
    # GET /api/v1/core/places/<place_id>/
    path("places/<str:place_id>/",     PlaceDetailAPIView.as_view(),     name="place_detail"),

    # GET /api/v1/core/categorias/
    path("categorias/", CategoryListAPIView.as_view(), name="category_list"),

    # ── Eventos ───────────────────────────────────────────────────────── #
    # GET /api/v1/core/events/
    path("events/",                  EventListAPIView.as_view(),   name="event_list"),
    # GET /api/v1/core/events/<event_id>/
    path("events/<str:event_id>/",   EventDetailAPIView.as_view(), name="event_detail"),

    # ── Restaurantes ──────────────────────────────────────────────────── #
    # GET /api/v1/core/restaurants/
    # GET /api/v1/core/restaurants/?lat=20.67&lng=-103.34&max_distance=2000
    path("restaurants/",                        RestaurantListAPIView.as_view(),   name="restaurant_list"),
    # GET /api/v1/core/restaurants/<restaurant_id>/
    path("restaurants/<str:restaurant_id>/",    RestaurantDetailAPIView.as_view(), name="restaurant_detail"),
]
