"""core/services/notification_service.py — Servicio de despacho de notificaciones masivas.

Separa la lógica de negocio del endpoint HTTP de admin.
Se llama tras crear un recurso para notificar a todos los turistas activos.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

RESOURCE_MESSAGES = {
    "places": {
        "titulo": "🗺️ ¡Nuevo destino en Tu-Turismo!",
        "mensaje_tpl": "Descubre '{nombre}' en {municipio}. ¡Un nuevo atractivo turístico te espera!",
        "tipo": "info",
    },
    "restaurants": {
        "titulo": "🍽️ ¡Nueva experiencia gastronómica!",
        "mensaje_tpl": "Conoce '{nombre}', el nuevo restaurante en tu catálogo favorito. ¡Dale una probada!",
        "tipo": "info",
    },
    "events": {
        "titulo": "🎉 ¡Nuevo evento en Jalisco!",
        "mensaje_tpl": "'{nombre}' ya está en la agenda. ¡No te lo pierdas!",
        "tipo": "info",
    },
}


def dispatch_resource_created(
    resource_type: str,
    resource_doc: Any,
    admin_id: str | None = None,
) -> int:
    """Despacha notificaciones masivas a todos los turistas activos cuando se crea un recurso.

    Args:
        resource_type: Tipo de recurso ('places', 'restaurants', 'events').
        resource_doc: Documento creado (dataclass con atributos).
        admin_id: ID del admin creador (se excluye de las notificaciones).

    Returns:
        Cantidad de notificaciones enviadas.
    """
    template = RESOURCE_MESSAGES.get(resource_type)
    if not template:
        logger.warning("dispatch_resource_created: tipo '%s' no reconocido.", resource_type)
        return 0

    try:
        from core.repositories.users import UserRepository
        from core.repositories.notifications import NotificationRepository

        # Obtener el nombre del recurso de forma defensiva
        nombre = getattr(resource_doc, "nombre", None) or "nuevo recurso"
        municipio = getattr(resource_doc, "municipio", None) or "Jalisco"
        resource_id = getattr(resource_doc, "id", None) or ""

        mensaje = template["mensaje_tpl"].format(nombre=nombre, municipio=municipio)

        user_repo = UserRepository()
        tourist_ids = user_repo.get_active_tourist_ids(exclude_id=admin_id)

        if not tourist_ids:
            logger.info("dispatch_resource_created: sin turistas activos para notificar.")
            return 0

        notif_repo = NotificationRepository()
        count = notif_repo.bulk_create_notifications(
            user_ids=tourist_ids,
            titulo=template["titulo"],
            mensaje=mensaje,
            tipo=template["tipo"],
            metadata={
                "recurso_id": resource_id,
                "recurso_tipo": resource_type,
            },
        )
        logger.info(
            "dispatch_resource_created: %d notificaciones enviadas para recurso '%s' (tipo=%s).",
            count, nombre, resource_type,
        )
        return count

    except Exception as exc:  # noqa: BLE001
        logger.error("Error en dispatch_resource_created (tipo=%s): %s", resource_type, exc)
        return 0
