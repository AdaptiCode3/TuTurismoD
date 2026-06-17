"""
core/repositories/base.py
==========================
Repositorio Base Abstracto — Patrón Repository con PyMongo nativo.

¿Por qué un repositorio abstracto?
------------------------------------
Desacopla la lógica de negocio de los detalles de acceso a MongoDB.
Cada colección tendrá su propio repositorio concreto que hereda esta
interfaz, garantizando consistencia en las operaciones CRUD y
facilitando mocking/testing sin tocar la base de datos real.

RESTRICCIÓN DE SEGURIDAD: Este módulo NO ejecuta ningún comando DDL
(createCollection, createIndex con opciones de validación de esquema,
dropCollection, etc.) sobre la base de datos existente.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError

from core.database import MongoDBClient

logger = logging.getLogger(__name__)

# Variable de tipo genérica que los repositorios concretos especializan.
# Representa el "modelo de Python" que devuelve cada repositorio (dict, dataclass, etc.)
T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """
    Repositorio base abstracto para colecciones MongoDB existentes.

    Cada repositorio concreto debe:
      1. Llamar super().__init__(collection_name) con el nombre exacto
         de la colección en la base de datos.
      2. Implementar el método _map_document() para transformar el
         documento BSON crudo en el tipo T de Python.

    Convenciones:
      - El campo '_id' de MongoDB siempre se convierte a string bajo la
        clave 'id' en el dict resultante, eliminando la dependencia de
        ObjectId fuera de esta capa.
      - Los métodos devuelven None (o lista vacía) ante ausencia de datos;
        lanzan RuntimeError sólo ante errores de infraestructura graves.
    """

    def __init__(self, collection_name: str) -> None:
        """
        Inicializa el repositorio conectándose a la colección indicada.

        Args:
            collection_name: Nombre exacto de la colección en MongoDB
                             (debe existir previamente en la base de datos).
        """
        self._collection_name: str = collection_name
        self._db: Database = MongoDBClient.get_database()
        self._collection: Collection = self._db[collection_name]
        logger.debug(
            "Repositorio inicializado → colección: '%s'", collection_name
        )

    # ------------------------------------------------------------------ #
    # Métodos de Mapeo (abstractos — responsabilidad del repositorio hijo)
    # ------------------------------------------------------------------ #

    @abstractmethod
    def _map_document(self, document: dict[str, Any]) -> T:
        """
        Transforma un documento BSON crudo en el tipo de salida T.

        Implementa aquí la tolerancia a campos faltantes usando .get()
        con valores por defecto, para soportar esquemas flexibles /
        documentos históricos con estructura variable.

        Args:
            document: Documento MongoDB tal como lo devuelve PyMongo.

        Returns:
            Instancia de T con los datos limpios y tipados.
        """
        ...

    # ------------------------------------------------------------------ #
    # Utilidades Internas
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_object_id(id_str: str) -> Optional[ObjectId]:
        """
        Convierte un string a ObjectId de manera segura.

        Args:
            id_str: Representación hexadecimal de 24 caracteres del ObjectId.

        Returns:
            ObjectId si la conversión es válida, None en caso contrario.
        """
        try:
            return ObjectId(id_str)
        except (InvalidId, TypeError) as exc:
            logger.warning("ID inválido para convertir a ObjectId: '%s' → %s", id_str, exc)
            return None

    @staticmethod
    def _serialize_id(document: dict[str, Any]) -> dict[str, Any]:
        """
        Reemplaza el campo '_id' (ObjectId) por 'id' (string) en el documento.
        Trabaja sobre una copia para no mutar el dict original de PyMongo.

        Args:
            document: Documento BSON crudo con clave '_id'.

        Returns:
            Nuevo dict con '_id' removido e 'id' como string.
        """
        doc = dict(document)
        raw_id = doc.pop("_id", None)
        doc["id"] = str(raw_id) if raw_id is not None else None
        return doc

    # ------------------------------------------------------------------ #
    # Operaciones CRUD — Implementaciones Base con PyMongo
    # ------------------------------------------------------------------ #

    def get_all(
        self,
        query: Optional[dict[str, Any]] = None,
        limit: int = 100,
        skip: int = 0,
        sort_by: Optional[str] = None,
        sort_order: int = 1,
    ) -> list[T]:
        """
        Recupera todos los documentos de la colección (con paginación).

        Args:
            query:      Filtro PyMongo opcional (ej. {"categoria": "Playas"}).
                        Si es None, devuelve todos los documentos.
            limit:      Máximo de documentos a devolver (default 100).
            skip:       Documentos a saltar para paginación (default 0).
            sort_by:    Campo por el que ordenar (ej. "nombre").
            sort_order: 1 = ascendente, -1 = descendente (default 1).

        Returns:
            Lista de objetos T mapeados desde los documentos encontrados.
            Lista vacía si no hay resultados o si hay un error de DB.
        """
        filter_query: dict[str, Any] = query or {}

        try:
            cursor = self._collection.find(filter_query).skip(skip).limit(limit)

            if sort_by:
                cursor = cursor.sort(sort_by, sort_order)

            return [
                self._map_document(self._serialize_id(doc))
                for doc in cursor
            ]

        except PyMongoError as exc:
            logger.error(
                "Error en get_all() [colección: %s]: %s",
                self._collection_name,
                exc,
            )
            return []

    def get_by_id(self, id_str: str) -> Optional[T]:
        """
        Busca un documento por su _id de MongoDB.

        Args:
            id_str: Representación string del ObjectId (24 hex chars).

        Returns:
            Objeto T mapeado si se encuentra el documento, None si no existe
            o si el ID proporcionado es inválido.
        """
        object_id = self._to_object_id(id_str)
        if object_id is None:
            return None

        try:
            document = self._collection.find_one({"_id": object_id})
            if document is None:
                logger.info(
                    "Documento no encontrado [colección: %s, id: %s]",
                    self._collection_name,
                    id_str,
                )
                return None

            return self._map_document(self._serialize_id(document))

        except PyMongoError as exc:
            logger.error(
                "Error en get_by_id() [colección: %s, id: %s]: %s",
                self._collection_name,
                id_str,
                exc,
            )
            return None

    def insert(self, data: dict[str, Any]) -> Optional[str]:
        """
        Inserta un nuevo documento en la colección.

        NOTA: NO ejecuta ninguna validación de esquema a nivel de servidor
        MongoDB. La validación debe realizarse en la capa de servicio/vista.

        Args:
            data: Diccionario con los campos del nuevo documento.
                  No debe incluir '_id'; MongoDB lo genera automáticamente.

        Returns:
            String con el nuevo ObjectId si la inserción fue exitosa,
            None si ocurre un error.
        """
        try:
            result = self._collection.insert_one(data)
            new_id = str(result.inserted_id)
            logger.info(
                "Documento insertado [colección: %s, id: %s]",
                self._collection_name,
                new_id,
            )
            return new_id

        except PyMongoError as exc:
            logger.error(
                "Error en insert() [colección: %s]: %s",
                self._collection_name,
                exc,
            )
            return None

    def update(self, id_str: str, data: dict[str, Any]) -> bool:
        """
        Actualiza parcialmente un documento existente ($set).

        Usa $set deliberadamente: sólo modifica los campos especificados
        sin sobrescribir el documento completo, lo cual es más seguro para
        esquemas flexibles con campos históricos variables.

        Args:
            id_str: ObjectId del documento a actualizar (como string).
            data:   Diccionario con los campos a modificar.

        Returns:
            True si se modificó al menos un documento, False en caso contrario.
        """
        object_id = self._to_object_id(id_str)
        if object_id is None:
            return False

        try:
            result = self._collection.update_one(
                {"_id": object_id},
                {"$set": data},
            )
            modified = result.modified_count > 0
            if modified:
                logger.info(
                    "Documento actualizado [colección: %s, id: %s]",
                    self._collection_name,
                    id_str,
                )
            else:
                logger.warning(
                    "update() no modificó ningún documento [colección: %s, id: %s]",
                    self._collection_name,
                    id_str,
                )
            return modified

        except PyMongoError as exc:
            logger.error(
                "Error en update() [colección: %s, id: %s]: %s",
                self._collection_name,
                id_str,
                exc,
            )
            return False

    def delete(self, id_str: str) -> bool:
        """
        Elimina un documento por su ObjectId.

        Args:
            id_str: ObjectId del documento a eliminar (como string).

        Returns:
            True si se eliminó exactamente un documento, False si no
            se encontró o si ocurrió un error.
        """
        object_id = self._to_object_id(id_str)
        if object_id is None:
            return False

        try:
            result = self._collection.delete_one({"_id": object_id})
            deleted = result.deleted_count > 0
            if deleted:
                logger.info(
                    "Documento eliminado [colección: %s, id: %s]",
                    self._collection_name,
                    id_str,
                )
            else:
                logger.warning(
                    "delete() no encontró el documento [colección: %s, id: %s]",
                    self._collection_name,
                    id_str,
                )
            return deleted

        except PyMongoError as exc:
            logger.error(
                "Error en delete() [colección: %s, id: %s]: %s",
                self._collection_name,
                id_str,
                exc,
            )
            return False

    def count(self, query: Optional[dict[str, Any]] = None) -> int:
        """
        Cuenta documentos en la colección, opcionalmente con filtro.

        Args:
            query: Filtro PyMongo (None = contar todos).

        Returns:
            Número de documentos que cumplen el filtro, 0 ante errores.
        """
        filter_query: dict[str, Any] = query or {}
        try:
            return self._collection.count_documents(filter_query)
        except PyMongoError as exc:
            logger.error(
                "Error en count() [colección: %s]: %s",
                self._collection_name,
                exc,
            )
            return 0
