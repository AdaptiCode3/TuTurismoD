"""
core/urls.py
============
Rutas de la aplicación core.
Expone el endpoint de health-check para verificar la conectividad con MongoDB.
"""
from django.urls import path
from core import views

app_name = "core"

urlpatterns = [
    # GET /api/v1/core/health/
    # Verifica que el servidor Django y la conexión a MongoDB están operativos.
    path("health/", views.health_check, name="health_check"),
]
