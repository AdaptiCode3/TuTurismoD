"""
core/database.py
================
Cliente MongoDB implementado con el Patrón Singleton.

¿Por qué Singleton?
-------------------
Un cliente de base de datos mantiene un pool de conexiones TCP hacia el servidor
de MongoDB. Crear múltiples instancias de MongoClient en una aplicación web
significaría abrir múltiples pools de conexiones, desperdiciando recursos de red
y memoria, y arriesgando superar los límites del cluster (especialmente en
MongoDB Atlas, que tiene cuotas de conexiones por tier).

El Singleton garantiza que, sin importar cuántas veces se llame a
MongoDBClient(), siempre se devuelva la misma instancia ya conectada,
compartiendo el mismo pool de conexiones de forma thread-safe.

Referencia: https://www.mongodb.com/docs/drivers/pymongo/#connect-to-mongodb
"""
from __future__ import annotations

import logging
from typing import Optional

import pymongo
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ConfigurationError

logger = logging.getLogger(__name__)


class MongoDBClient:
    """
    Cliente MongoDB Singleton.

    Uso:
        db = MongoDBClient.get_database()
        collection = db["destinos"]
    """

    # ------------------------------------------------------------------ #
    # Atributos de clase — compartidos por TODAS las instancias (Singleton)
    # ------------------------------------------------------------------ #
    _instance: Optional["MongoDBClient"] = None
    _client: Optional[MongoClient] = None
    _database: Optional[Database] = None

    def __new__(cls) -> "MongoDBClient":
        """
        Sobrescribimos __new__ para controlar la creación de instancias.
        Si ya existe una instancia previa, la devolvemos directamente
        sin ejecutar __init__ de nuevo.
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """
        Inicializa la conexión sólo en la primera instanciación.
        Las llamadas subsiguientes retornan sin hacer nada gracias al
        guard '_client is not None'.
        """
        if MongoDBClient._client is not None:
            # Conexión ya establecida; no hacer nada.
            return
        self._connect()

    def _connect(self) -> None:
        """
        Establece la conexión con MongoDB usando las variables de entorno
        cargadas previamente en settings.py.

        Captura explícitamente:
        - ConnectionFailure: el cluster no responde (red, credenciales, etc.)
        - ConfigurationError: URI malformado u opción inválida en MongoClient.
        """
        from django.conf import settings  # Import tardío para evitar circular imports

        mongo_uri: str = settings.MONGO_URI
        db_name: str = settings.MONGO_DB_NAME

        try:
            # serverSelectionTimeoutMS: tiempo máximo (ms) que PyMongo espera
            # para seleccionar un servidor antes de lanzar ConnectionFailure.
            # 5 000 ms es suficiente para desarrollo; en producción considera 10 000.
            MongoDBClient._client = MongoClient(
                mongo_uri,
                serverSelectionTimeoutMS=5_000,
            )

            # 'ping' es un comando administrativo ligero que fuerza la
            # verificación real de la conexión en el momento del arranque.
            MongoDBClient._client.admin.command("ping")

            MongoDBClient._database = MongoDBClient._client[db_name]

            logger.info(
                "✅ MongoDB conectado exitosamente → base de datos: '%s'", db_name
            )

        except ConnectionFailure as exc:
            # El cluster no responde: registramos el error pero NO lanzamos
            # una excepción no controlada, para evitar que el proceso Django
            # colapse al arrancar. Las vistas deberán manejar _database = None.
            logger.critical(
                "❌ No se pudo conectar a MongoDB (%s): %s",
                mongo_uri,
                exc,
            )
            MongoDBClient._client = None
            MongoDBClient._database = None

        except ConfigurationError as exc:
            logger.critical(
                "❌ URI de MongoDB mal configurado: %s", exc
            )
            MongoDBClient._client = None
            MongoDBClient._database = None

    # ------------------------------------------------------------------ #
    # API Pública
    # ------------------------------------------------------------------ #

    @classmethod
    def get_database(cls) -> Database:
        """
        Devuelve la instancia de Database de PyMongo.

        Raises:
            RuntimeError: si la conexión no está disponible (ej. cluster caído).
        """
        # Garantiza que la instancia Singleton se haya inicializado al menos una vez.
        cls()

        if cls._database is None:
            raise RuntimeError(
                "La base de datos MongoDB no está disponible. "
                "Verifica la variable MONGO_URI en tu archivo .env y que el "
                "cluster esté en línea."
            )
        return cls._database

    @classmethod
    def get_client(cls) -> MongoClient:
        """
        Devuelve el MongoClient subyacente (útil para operaciones de sesión
        o transacciones multi-documento).

        Raises:
            RuntimeError: si el cliente no está disponible.
        """
        cls()

        if cls._client is None:
            raise RuntimeError(
                "El cliente MongoDB no está disponible. "
                "Verifica la variable MONGO_URI en tu archivo .env."
            )
        return cls._client

    @classmethod
    def close(cls) -> None:
        """
        Cierra el pool de conexiones de forma limpia.
        Útil en tests o en señales de apagado de Django.
        """
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._database = None
            cls._instance = None
            logger.info("🔌 Conexión MongoDB cerrada.")
