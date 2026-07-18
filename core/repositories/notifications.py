"""core/repositories/notifications.py — Repositorio de notificaciones en PyMongo nativo."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo.errors import PyMongoError

from core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

NOTIFICATIONS_COLLECTION = "notifications"


@dataclass
class NotificationDocument:
    """Representación tipada de un documento en la colección notifications."""

    id: Optional[str] = None
    user_id: str = ""
    titulo: str = ""
    mensaje: str = ""
    leido: bool = False
    tipo: str = "info"
    created_at: str = ""


class NotificationRepository(BaseRepository[NotificationDocument]):
    """Repositorio concreto para notificaciones de usuario en MongoDB."""

    def __init__(self) -> None:
        super().__init__(NOTIFICATIONS_COLLECTION)

    def _map_document(self, document: dict[str, Any]) -> NotificationDocument:
        doc_id = document.get("id")
        try:
            return NotificationDocument(
                id=doc_id,
                user_id=str(document.get("user_id", "")),
                titulo=str(document.get("titulo", "")),
                mensaje=str(document.get("mensaje", "")),
                leido=bool(document.get("leido", False)),
                tipo=str(document.get("tipo", "info")),
                created_at=str(document.get("created_at", "")),
            )
        except Exception as exc:
            logger.warning("Error mapeando notificación id=%s: %s", doc_id, exc)
            return NotificationDocument(id=doc_id)

    def get_by_user(self, user_id: str, limit: int = 50) -> list[NotificationDocument]:
        """Devuelve notificaciones del usuario ordenadas descendente por created_at."""
        return self.get_all(
            query={"user_id": user_id},
            limit=limit,
            sort_by="-created_at",
        )

    def create_notification(
        self, user_id: str, titulo: str, mensaje: str, tipo: str = "info"
    ) -> Optional[NotificationDocument]:
        """Crea una nueva notificación para un usuario."""
        now = datetime.now(tz=timezone.utc).isoformat()
        data = {
            "user_id": user_id,
            "titulo": titulo,
            "mensaje": mensaje,
            "leido": False,
            "tipo": tipo,
            "created_at": now,
        }
        new_id = self.insert(data)
        if not new_id:
            return None
        return self.get_by_id(new_id)

    def mark_as_read(self, user_id: str, notification_id: str) -> Optional[NotificationDocument]:
        """Marca una notificación como leída verificando que pertenezca al usuario."""
        doc = self.get_by_id(notification_id)
        if not doc or doc.user_id != user_id:
            return None
        self.update(notification_id, {"leido": True})
        return self.get_by_id(notification_id)

    def mark_all_as_read(self, user_id: str) -> int:
        """Marca todas las notificaciones de un usuario como leídas."""
        try:
            res = self._collection.update_many(
                {"user_id": user_id, "leido": False},
                {"$set": {"leido": True}},
            )
            return res.modified_count
        except PyMongoError as exc:
            logger.error("Error en mark_all_as_read(user_id=%s): %s", user_id, exc)
            return 0

    def delete_for_user(self, user_id: str, notification_id: str) -> bool:
        """Elimina una notificación verificando que pertenezca al usuario."""
        doc = self.get_by_id(notification_id)
        if not doc or doc.user_id != user_id:
            return False
        return self.delete(notification_id)

    def delete_all_for_user(self, user_id: str) -> int:
        """Elimina todas las notificaciones de un usuario."""
        try:
            res = self._collection.delete_many({"user_id": user_id})
            return res.deleted_count
        except PyMongoError as exc:
            logger.error("Error en delete_all_for_user(user_id=%s): %s", user_id, exc)
            return 0
