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

from core.views import health_check, upload_image
from core.views.auth import login, me, refresh_token, register
from core.views.favorites import favorites_delete, favorites_list_create
from core.views.admin import resource_create, resource_update, resource_delete
from core.views.stats import admin_stats, admin_spatial_density
from core.views.backup import backup_export
from core.views.notifications import (
    notifications_list_create_delete,
    notification_mark_all_read,
    notification_mark_read,
    notification_detail,
)
from core.views.places import (
    PlaceCategoriasAPIView,
    PlaceDetailAPIView,
    PlaceListAPIView,
    PlaceMunicipiosAPIView,
    PlaceTopRatedAPIView,
)
from core.views.restaurants import (
    RestaurantDetailAPIView,
    RestaurantListAPIView,
)
from core.views.categories import CategoryListAPIView
from core.views.events import EventDetailAPIView, EventListAPIView
from core.views.users import users_list_create, user_detail, send_user_recommendations
from core.views.password_recovery import send_recovery_code, verify_recovery_code, reset_password

app_name = "core"

urlpatterns = [
    # ── Sistema ───────────────────────────────────────────────────────── #
    # GET /api/v1/core/health/
    path("health/", health_check, name="health_check"),
    # POST /api/v1/core/upload/
    path("upload/", upload_image, name="upload_image"),

    # ── Autenticación JWT ─────────────────────────────────────────────── #
    # POST /api/v1/core/auth/login/
    path("auth/login/",    login,         name="auth_login"),
    # POST /api/v1/core/auth/register/
    path("auth/register/", register,      name="auth_register"),
    # POST /api/v1/core/auth/refresh/
    path("auth/refresh/",  refresh_token, name="auth_refresh"),
    # GET/PUT/PATCH  /api/v1/core/auth/me/
    path("auth/me/",       me,            name="auth_me"),

    # POST /api/v1/core/auth/password/send-code/ (y opcional sin barra)
    path("auth/password/send-code",   send_recovery_code,   name="password_send_code"),
    path("auth/password/send-code/",  send_recovery_code,   name="password_send_code_slash"),
    path("auth/password/verify-code", verify_recovery_code, name="password_verify_code"),
    path("auth/password/verify-code/", verify_recovery_code, name="password_verify_code_slash"),
    path("auth/password/reset",       reset_password,       name="password_reset"),
    path("auth/password/reset/",      reset_password,       name="password_reset_slash"),

    # ── Lugares turísticos ────────────────────────────────────────────── #
    # GET /api/v1/core/places/
    # GET /api/v1/core/places/?lat=20.67&lng=-103.34&max_distance=5000
    path("places/",                    PlaceListAPIView.as_view(),       name="place_list"),
    # GET /api/v1/core/places/categorias/
    path("places/categorias/",         PlaceCategoriasAPIView.as_view(), name="place_categorias"),
    # GET /api/v1/core/places/municipios/
    path("places/municipios/",         PlaceMunicipiosAPIView.as_view(), name="place_municipios"),
    # GET /api/v1/core/places/top-rated/
    path("places/top-rated/",          PlaceTopRatedAPIView.as_view(),   name="place_top_rated"),
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

    # ── Favoritos ────────────────────────────────────────────────────── #
    # GET  /api/v1/core/favorites/                → Lista favoritos del usuario
    # POST /api/v1/core/favorites/                → Agrega un favorito
    path("favorites/",                           favorites_list_create,            name="favorites_list_create"),
    # DELETE /api/v1/core/favorites/<referencia_id>/  → Elimina un favorito
    path("favorites/<str:referencia_id>/",       favorites_delete,                 name="favorites_delete"),

    # ── Notificaciones ───────────────────────────────────────────────── #
    # GET/POST/DELETE /api/v1/core/notifications/
    path("notifications/",                                 notifications_list_create_delete, name="notifications_list_create_delete"),
    # PATCH /api/v1/core/notifications/read-all/ (debe ir antes de <notification_id>/)
    path("notifications/read-all/",                        notification_mark_all_read,       name="notification_mark_all_read"),
    # PATCH /api/v1/core/notifications/<id>/read/
    path("notifications/<str:notification_id>/read/",    notification_mark_read,           name="notification_mark_read"),
    # DELETE /api/v1/core/notifications/<id>/
    path("notifications/<str:notification_id>/",          notification_detail,              name="notification_detail"),

    # ── Admin: rutas fijas antes de las paramétricas ─────────────── #
    path("admin/stats/",                                   admin_stats,             name="admin_stats"),
    path("admin/spatial-density/",                         admin_spatial_density,   name="admin_spatial_density"),
    path("admin/users/",                                   users_list_create,       name="admin_users_list_create"),
    path("admin/users/<str:user_id>/",                     user_detail,             name="admin_user_detail"),
    path("admin/backup/<str:resource>/",                   backup_export,           name="admin_backup_export"),
    path("users/send-recommendations/",                    send_user_recommendations, name="user_send_recommendations"),

    # ── Admin CRUD genérico (sólo rol admin) ─────────────────────── #
    path("admin/<str:resource>/",                          resource_create,         name="admin_resource_create"),
    path("admin/<str:resource>/<str:resource_id>/",        resource_update,         name="admin_resource_update"),
    path("admin/<str:resource>/<str:resource_id>/delete/", resource_delete,         name="admin_resource_delete"),
]
