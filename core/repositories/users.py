"""
core/repositories/users.py
============================
Repositorio de usuarios — conecta con la colección existente en MongoDB.

RESTRICCIÓN CRÍTICA: Este módulo NO importa ni usa
  django.contrib.auth.models.User ni ningún modelo Django ORM.
  Todo acceso a datos es exclusivamente mediante PyMongo nativo.

Mapeo defensivo: igual que PlaceRepository, todos los campos usan
.get() con valores por defecto para tolerar documentos históricos
con estructura variable en la colección de usuarios.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from pymongo.errors import PyMongoError

from core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Nombre de la colección en MongoDB — colección real en producción
# --------------------------------------------------------------------------- #
USERS_COLLECTION_NAME = "usuarios"

# Regex de validación de email (RFC 5322 simplificado)
_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


# --------------------------------------------------------------------------- #
# Modelo de datos Python — estructura canónica de un usuario
# --------------------------------------------------------------------------- #

@dataclass
class UserDocument:
    """
    Representación tipada de un documento de la colección 'usuarios' de MongoDB.

    Estructura real de los documentos en producción:
        _id      : ObjectId (serializado a 'id' como string)
        email    : String, único — identificador principal
        password : String — hash bcrypt generado externamente
        rol      : String — 'admin' | 'turista'

    IMPORTANTE: El campo `password_hash` (que mapea al campo 'password'
    de MongoDB) NUNCA debe incluirse en las respuestas JSON de las APIs.
    Usa to_safe_dict() para serializar de forma segura hacia el frontend.

    Campos:
        id            : ObjectId serializado como string.
        email         : Correo electrónico (identificador principal).
        password_hash : Hash bcrypt del campo 'password' de MongoDB.
                        NUNCA exponer en API — solo para verificación interna.
        nombre        : Nombre completo (puede no existir en docs históricos).
        rol           : Rol del usuario: 'admin' o 'turista'.
        activo        : Flag de bloqueo lógico de cuenta (default True).
        created_at    : Timestamp ISO de creación.
        last_login    : Timestamp ISO del último inicio de sesión.
        preferences   : Preferencias adicionales (dict flexible).
    """
    id: Optional[str] = None
    email: str = ""
    password_hash: str = ""          # ← mapea al campo 'password' en MongoDB
    nombre: str = ""
    rol: str = "turista"             # 'admin' | 'turista'
    activo: bool = True
    created_at: Optional[str] = None
    last_login: Optional[str] = None
    preferences: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializa incluyendo todos los campos (uso INTERNO únicamente)."""
        return asdict(self)

    def to_safe_dict(self) -> dict[str, Any]:
        """
        Serializa excluyendo password_hash.

        Usa SIEMPRE este método al enviar datos de usuario al frontend.
        """
        data = asdict(self)
        data.pop("password_hash", None)
        return data

    def __repr__(self) -> str:
        return f"<UserDocument id={self.id!r} email={self.email!r} rol={self.rol!r}>"


# --------------------------------------------------------------------------- #
# Repositorio concreto
# --------------------------------------------------------------------------- #

class UserRepository(BaseRepository[UserDocument]):
    """
    Repositorio para la colección de usuarios existente en MongoDB.

    Hereda todas las operaciones CRUD de BaseRepository y especializa:
      - _map_document(): transforma BSON → UserDocument de forma defensiva.
      - get_by_email(): búsqueda case-insensitive por correo (uso principal
        en el flujo de login).
      - email_exists(): verificación de unicidad para registro.
      - update_last_login(): actualiza el timestamp de último acceso.

    Uso en flujo de login:
        repo = UserRepository()
        user = repo.get_by_email("turista@jalisco.mx")
        if user and PasswordService.verify(password, user.password_hash):
            token = JWTService.encode({"id": user.id, "rol": user.rol})
    """

    def __init__(self) -> None:
        """Inicializa conectándose a la colección de usuarios existente."""
        super().__init__(USERS_COLLECTION_NAME)

    # ------------------------------------------------------------------ #
    # Implementación del mapeo BSON → UserDocument
    # ------------------------------------------------------------------ #

    def _map_document(self, document: dict[str, Any]) -> UserDocument:
        """
        Convierte un documento MongoDB crudo en un UserDocument tipado.

        Estrategia de tolerancia a fallos:
          - .get() con default en todos los campos.
          - Acepta variantes de nombre de campo (email / correo, nombre / name).
          - Normaliza el email a minúsculas para consistencia.
          - Si el campo 'rol' tiene un valor inesperado, cae al default 'turista'.
          - En caso de excepción irrecuperable, devuelve UserDocument mínimo
            con el id para trazabilidad en logs.

        Args:
            document: Dict con '_id' serializado a 'id', tal como lo
                      entrega BaseRepository._serialize_id().
        """
        doc_id = document.get("id")
        ROLES_VALIDOS = {"turista", "admin", "operador", "guia"}

        try:
            # Email: aceptar variantes y normalizar a minúsculas
            raw_email = (
                document.get("email")
                or document.get("correo")
                or document.get("mail")
                or ""
            )
            email = str(raw_email).strip().lower()

            # Rol: validar contra whitelist; caer a "turista" si inválido
            raw_rol = str(document.get("rol") or document.get("role") or "turista").lower()
            rol = raw_rol if raw_rol in ROLES_VALIDOS else "turista"

            # Nombre: aceptar variantes
            nombre = str(
                document.get("nombre")
                or document.get("name")
                or document.get("full_name")
                or document.get("display_name")
                or ""
            ).strip()

            # Preferences: solo aceptar dict, ignorar si es otro tipo
            raw_prefs = document.get("preferences") or document.get("preferencias") or {}
            preferences = raw_prefs if isinstance(raw_prefs, dict) else {}

            # Timestamps: convertir a string si son datetime de Python
            def _ts_to_str(val: Any) -> Optional[str]:
                if val is None:
                    return None
                try:
                    return val.isoformat() if hasattr(val, "isoformat") else str(val)
                except Exception:  # noqa: BLE001
                    return None

            return UserDocument(
                id=doc_id,
                email=email,
                # 'password' es el nombre real del campo en la colección 'usuarios'
                password_hash=str(
                    document.get("password")
                    or document.get("password_hash")
                    or document.get("hashed_password")
                    or ""
                ),
                nombre=nombre,
                rol=rol,
                activo=bool(document.get("activo", True)),
                created_at=_ts_to_str(
                    document.get("created_at") or document.get("createdAt")
                ),
                last_login=_ts_to_str(
                    document.get("last_login") or document.get("lastLogin")
                ),
                preferences=preferences,
            )

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error al mapear UserDocument id=%s: %s", doc_id, exc
            )
            return UserDocument(id=doc_id)

    # ------------------------------------------------------------------ #
    # Consultas específicas del dominio de autenticación
    # ------------------------------------------------------------------ #

    def get_user_by_email(self, email: str) -> Optional[UserDocument]:
        """
        Busca un usuario en la colección 'usuarios' por su email.

        Método principal para el flujo de autenticación. La búsqueda usa
        regex case-insensitive sobre el campo 'email' para tolerar
        variantes de capitalización en documentos históricos.

        Args:
            email: Correo electrónico a buscar (ej. "turista@jalisco.mx").

        Returns:
            UserDocument si existe el usuario, None si no se encuentra
            o si el email tiene formato inválido.
        """
        email = email.strip().lower()
        if not _EMAIL_REGEX.match(email):
            logger.warning(
                "get_user_by_email() recibió email con formato inválido: '%s'", email
            )
            return None

        try:
            # Búsqueda directa sobre el campo 'email' de la colección 'usuarios'
            document = self._collection.find_one(
                {"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}
            )

            if document is None:
                logger.info("Usuario no encontrado para email: '%s'", email)
                return None

            return self._map_document(self._serialize_id(document))

        except PyMongoError as exc:
            logger.error("Error en get_user_by_email('%s'): %s", email, exc)
            return None

    def get_by_email(self, email: str) -> Optional[UserDocument]:
        """Alias de get_user_by_email() para compatibilidad interna."""
        return self.get_user_by_email(email)

    def email_exists(self, email: str) -> bool:
        """
        Verifica si ya existe un usuario con el email dado (para registro).

        Más eficiente que get_by_email() porque sólo cuenta documentos
        sin cargar el documento completo.

        Args:
            email: Correo a verificar.

        Returns:
            True si ya existe una cuenta con ese email, False en caso contrario.
        """
        email = email.strip().lower()
        if not _EMAIL_REGEX.match(email):
            return False

        try:
            count = self._collection.count_documents({
                "$or": [
                    {"email":  {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
                    {"correo": {"$regex": f"^{re.escape(email)}$", "$options": "i"}},
                ]
            }, limit=1)
            return count > 0
        except PyMongoError as exc:
            logger.error("Error en email_exists('%s'): %s", email, exc)
            return False

    def get_by_rol(self, rol: str) -> list[UserDocument]:
        """
        Devuelve todos los usuarios de un rol específico.

        Args:
            rol: Rol a filtrar ("turista", "admin", "operador", "guia").

        Returns:
            Lista de UserDocument del rol indicado.
        """
        return self.get_all(query={"rol": rol}, sort_by="nombre")

    def update_last_login(self, user_id: str) -> bool:
        """
        Actualiza el campo last_login del usuario al momento actual.

        Se llama automáticamente tras un login exitoso para auditoría.

        Args:
            user_id: String del ObjectId del usuario.

        Returns:
            True si se actualizó correctamente, False en caso contrario.
        """
        from datetime import datetime, timezone
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        return self.update(user_id, {"last_login": now_iso, "lastLogin": now_iso})

    def create_user(
        self,
        email: str,
        password_hash: str,
        nombre: str = "",
        rol: str = "turista",
    ) -> Optional[str]:
        """
        Registra un nuevo usuario en la colección.

        Verifica unicidad de email antes de insertar.

        Args:
            email:         Email del nuevo usuario (se normaliza a minúsculas).
            password_hash: Hash bcrypt de la contraseña (generado por PasswordService).
            nombre:        Nombre completo del usuario.
            rol:           Rol asignado (default "turista").

        Returns:
            String del nuevo ObjectId si el registro fue exitoso.
            None si el email ya existe o si ocurre un error de base de datos.
        """
        from datetime import datetime, timezone

        email = email.strip().lower()

        if self.email_exists(email):
            logger.warning(
                "Intento de registro con email duplicado: '%s'", email
            )
            return None

        user_doc = {
            "email": email,
            "password_hash": password_hash,
            "nombre": nombre.strip(),
            "rol": rol,
            "activo": True,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
            "last_login": None,
            "preferences": {},
        }

        new_id = self.insert(user_doc)
        if new_id:
            logger.info(
                "Nuevo usuario registrado → id=%s, email=%s, rol=%s",
                new_id, email, rol,
            )
        return new_id
