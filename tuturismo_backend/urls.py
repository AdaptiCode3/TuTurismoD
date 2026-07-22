"""
tuturismo_backend/urls.py
=========================
Enrutador raíz del proyecto Tu-Turismo.

Convención de rutas de la API:
  /api/v1/core/        → endpoints de salud y utilidades (app: core)
  /api/v1/destinos/    → endpoints de destinos turísticos (futura app: destinos)
  /api/v1/usuarios/    → endpoints de usuarios         (futura app: usuarios)
"""
from django.urls import path, include
from core.views import health_check

urlpatterns = [
    # ── Health check de plataforma en la nube (Render) ──────────────────────
    path("healthz", health_check, name="healthz_root"),
    path("api/v1/health/", health_check, name="health_api_root"),
    
    # ── API v1 ──────────────────────────────────────────────────────────────
    path("api/v1/auth/password/", include("core.urls_recovery")),
    path("api/v1/core/", include("core.urls")),
    # Las siguientes rutas se activarán en Fases posteriores del proyecto:
    # path("api/v1/destinos/", include("destinos.urls")),
    # path("api/v1/usuarios/", include("usuarios.urls")),
]
