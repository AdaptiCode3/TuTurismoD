"""
core/views/__init__.py
=======================
Paquete de vistas de la aplicación core.

Re-exporta las vistas base para mantener compatibilidad con el import
existente en core/urls.py:  `from core import views` → `views.health_check`
"""
from core.views.health import health_check  # noqa: F401
from core.views.upload import upload_image  # noqa: F401

__all__ = ["health_check", "upload_image"]
