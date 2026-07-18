"""
core/repositories/favorites.py
================================
Repositorio para la colección 'favorites' usando PyMongo nativo.

RESTRICCIÓN ARQUITECTÓNICA:
  - NO usa Django ORM ni modelos relacionales.
  - Acceso directo a MongoDB a través de BaseRepository[FavoriteDocument].

Estructura del documento en MongoDB:
  {
      "_id":          ObjectId,
      "user_id":      str,         # ObjectId del usuario como string
      "tipo":         str,         # "lugar" | "restaurante" | "evento"
      "referencia_id": str,        # ObjectId del recurso referenciado como string
      "created_at":   str          # ISO 8601
  }
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo.errors import PyMongoError

from core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

FAVORITES_COLLECTION = "favorites"

# Tipos válidos de recurso que se pueden marcar como favorito
VALID_TIPOS = {"lugar", "restaurante", "evento"}


@dataclass
class FavoriteDocument:
    """Representación tipada de un documento en la colección favorites."""

    id: Optional[str] = None
    user_id: str = ""
    tipo: str = ""                  # "lugar" | "restaurante" | "evento"
    referencia_id: str = ""         # ID del recurso favorito
    created_at: str = ""


class FavoriteRepository(BaseRepository[FavoriteDocument]):
    """
    Repositorio concreto para la colección 'favorites'.

    Gestiona operaciones de favoritos por usuario sin depender del ORM de Django.
    """

    def __init__(self) -> None:
        super().__init__(FAVORITES_COLLECTION)

    # ------------------------------------------------------------------ #
    # Mapeo BSON → FavoriteDocument
    # ------------------------------------------------------------------ #

    def _map_document(self, document: dict[str, Any]) -> FavoriteDocument:
        doc_id = document.get("id")
        try:
            return FavoriteDocument(
                id=doc_id,
                user_id=str(document.get("user_id", "")),
                tipo=str(document.get("tipo", "")),
                referencia_id=str(document.get("referencia_id", "")),
                created_at=str(document.get("created_at", "")),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Error al mapear favorito id=%s: %s", doc_id, exc)
            return FavoriteDocument(id=doc_id)

    # ------------------------------------------------------------------ #
    # Operaciones específicas de favoritos
    # ------------------------------------------------------------------ #

    def get_by_user(self, user_id: str) -> list[FavoriteDocument]:
        """
        Devuelve todos los favoritos de un usuario ordenados por fecha (más recientes primero).

        Args:
            user_id: ObjectId del usuario como string.

        Returns:
            Lista de FavoriteDocument. Lista vacía si el usuario no tiene favoritos.
        """
        try:
            cursor = self._collection.find(
                {"user_id": user_id}
            ).sort("created_at", -1)

            results: list[FavoriteDocument] = []
            for doc in cursor:
                results.append(self._map_document(self._serialize_id(doc)))
            return results
        except PyMongoError as exc:
            logger.error(
                "Error en get_by_user() [user_id=%s]: %s", user_id, exc
            )
            return []

    def get_by_user_and_tipo(
        self, user_id: str, tipo: str
    ) -> list[FavoriteDocument]:
        """
        Devuelve favoritos de un usuario filtrados por tipo de recurso.

        Args:
            user_id: ObjectId del usuario.
            tipo:    "lugar" | "restaurante" | "evento".

        Returns:
            Lista filtrada de FavoriteDocument.
        """
        try:
            cursor = self._collection.find(
                {"user_id": user_id, "tipo": tipo}
            ).sort("created_at", -1)

            return [
                self._map_document(self._serialize_id(doc)) for doc in cursor
            ]
        except PyMongoError as exc:
            logger.error(
                "Error en get_by_user_and_tipo() [user_id=%s, tipo=%s]: %s",
                user_id, tipo, exc,
            )
            return []

    def already_saved(self, user_id: str, referencia_id: str) -> bool:
        """
        Verifica si un recurso ya está en los favoritos del usuario.

        Args:
            user_id:       ObjectId del usuario como string.
            referencia_id: ObjectId del recurso como string.

        Returns:
            True si ya existe, False en caso contrario.
        """
        try:
            count = self._collection.count_documents(
                {"user_id": user_id, "referencia_id": referencia_id},
                limit=1,
            )
            return count > 0
        except PyMongoError as exc:
            logger.error(
                "Error en already_saved() [user_id=%s, ref=%s]: %s",
                user_id, referencia_id, exc,
            )
            return False

    def add_favorite(
        self, user_id: str, tipo: str, referencia_id: str
    ) -> Optional[FavoriteDocument]:
        """
        Agrega un recurso a los favoritos del usuario.

        Verifica duplicados antes de insertar para mantener consistencia.

        Args:
            user_id:       ObjectId del usuario como string.
            tipo:          Tipo de recurso ("lugar", "restaurante", "evento").
            referencia_id: ObjectId del recurso a marcar como favorito.

        Returns:
            FavoriteDocument recién creado, o None si ya existía o hubo error.
        """
        if tipo not in VALID_TIPOS:
            logger.warning(
                "Tipo de favorito inválido: '%s'. Debe ser uno de: %s",
                tipo, VALID_TIPOS,
            )
            return None

        if self.already_saved(user_id, referencia_id):
            logger.info(
                "Favorito ya existente [user_id=%s, ref=%s]", user_id, referencia_id
            )
            # Devuelve el documento existente
            try:
                doc = self._collection.find_one(
                    {"user_id": user_id, "referencia_id": referencia_id}
                )
                if doc:
                    return self._map_document(self._serialize_id(doc))
            except PyMongoError:
                pass
            return None

        fav_doc: dict[str, Any] = {
            "user_id":       user_id,
            "tipo":          tipo,
            "referencia_id": referencia_id,
            "created_at":    datetime.now(tz=timezone.utc).isoformat(),
        }

        new_id = self.insert(fav_doc)
        if new_id:
            return self.get_by_id(new_id)
        return None

    def remove_favorite(self, user_id: str, referencia_id: str) -> bool:
        """
        Elimina un favorito del usuario.

        Args:
            user_id:       ObjectId del usuario como string.
            referencia_id: ObjectId del recurso a eliminar de favoritos.

        Returns:
            True si se eliminó al menos un documento, False en caso contrario.
        """
        try:
            result = self._collection.delete_one(
                {"user_id": user_id, "referencia_id": referencia_id}
            )
            deleted = result.deleted_count > 0
            if deleted:
                logger.info(
                    "Favorito eliminado [user_id=%s, ref=%s]",
                    user_id, referencia_id,
                )
            else:
                logger.warning(
                    "remove_favorite() no encontró el documento "
                    "[user_id=%s, ref=%s]",
                    user_id, referencia_id,
                )
            return deleted
        except PyMongoError as exc:
            logger.error(
                "Error en remove_favorite() [user_id=%s, ref=%s]: %s",
                user_id, referencia_id, exc,
            )
            return False

    def remove_all_for_user(self, user_id: str) -> int:
        """
        Elimina TODOS los favoritos de un usuario.

        Útil para el borrado de cuentas.

        Args:
            user_id: ObjectId del usuario.

        Returns:
            Número de documentos eliminados.
        """
        try:
            result = self._collection.delete_many({"user_id": user_id})
            logger.info(
                "remove_all_for_user() eliminó %d favoritos [user_id=%s]",
                result.deleted_count, user_id,
            )
            return result.deleted_count
        except PyMongoError as exc:
            logger.error(
                "Error en remove_all_for_user() [user_id=%s]: %s",
                user_id, exc,
            )
            return 0
