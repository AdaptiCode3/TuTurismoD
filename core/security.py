"""
core/security.py
================
Motor de seguridad JWT para el proyecto Tu-Turismo.

Responsabilidades:
  1. JWTService  — Codifica y decodifica tokens JWT con PyJWT.
  2. PasswordService — Hash y verificación de contraseñas con bcrypt.
  3. @jwt_required  — Decorador que protege vistas Django sin ORM relacional.

RESTRICCIÓN CRÍTICA: Este módulo NO importa ni usa
  django.contrib.auth.models.User ni ningún modelo Django ORM.

Flujo del decorador:
  Request → Extrae "Authorization: Bearer <token>"
           → Decodifica con JWTService.decode()
           → Inyecta request.user_payload (dict) con {id, email, rol}
           → Continúa hacia la vista protegida
           → 401 si falta token, expiró o es inválido.
"""
from __future__ import annotations

import functools
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import bcrypt
import jwt
from django.conf import settings
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constantes de configuración
# --------------------------------------------------------------------------- #

# Algoritmo de firma — HS256 es estándar para secrets simétricos.
# Cambia a RS256 si en el futuro migras a llaves RSA asimétricas.
JWT_ALGORITHM = "HS256"

# Tiempo de vida del access token (24 horas)
ACCESS_TOKEN_TTL_HOURS = 24

# Header HTTP que se inspecciona
AUTH_HEADER = "HTTP_AUTHORIZATION"
BEARER_PREFIX = "Bearer "


# --------------------------------------------------------------------------- #
# 1. JWTService — Gestión de Tokens
# --------------------------------------------------------------------------- #

class JWTService:
    """
    Servicio estático para crear y validar JSON Web Tokens.

    El SECRET_KEY se lee de settings.SECRET_KEY (que a su vez lo carga
    desde la variable de entorno SECRET_KEY del archivo .env).

    Uso:
        token = JWTService.encode({"id": "abc123", "rol": "turista"})
        payload = JWTService.decode(token)   # → dict o None
    """

    @staticmethod
    def _get_secret() -> str:
        """Obtiene la clave secreta desde Django settings (cargada del .env)."""
        secret: str = getattr(settings, "SECRET_KEY", "")
        if not secret:
            raise RuntimeError(
                "SECRET_KEY no está configurada en las variables de entorno. "
                "Agrega SECRET_KEY=... a tu archivo .env"
            )
        return secret

    @classmethod
    def encode(
        cls,
        payload: dict[str, Any],
        ttl_hours: int = ACCESS_TOKEN_TTL_HOURS,
    ) -> str:
        """
        Genera un JWT firmado con HS256.

        El payload resultante incluye:
          - Todos los campos del dict recibido (id, email, rol, etc.)
          - 'iat': fecha de emisión (issued at)
          - 'exp': fecha de expiración (iat + ttl_hours)

        Args:
            payload:   Dict con los claims del usuario (id, rol, etc.).
                       NUNCA incluir la contraseña ni datos sensibles.
            ttl_hours: Tiempo de vida en horas (default 24).

        Returns:
            String del token JWT firmado.

        Raises:
            RuntimeError: Si SECRET_KEY no está configurada.
        """
        now = datetime.now(tz=timezone.utc)
        full_payload: dict[str, Any] = {
            **payload,
            "iat": now,
            "exp": now + timedelta(hours=ttl_hours),
        }

        token: str = jwt.encode(
            full_payload,
            cls._get_secret(),
            algorithm=JWT_ALGORITHM,
        )

        logger.info(
            "Token JWT generado para user_id=%s, expira en %d h",
            payload.get("id", "unknown"),
            ttl_hours,
        )
        return token

    @classmethod
    def decode(cls, token: str) -> Optional[dict[str, Any]]:
        """
        Decodifica y valida un JWT.

        Valida firma y expiración automáticamente. Devuelve None
        (en lugar de lanzar excepción) para simplificar el uso en
        el decorador @jwt_required.

        Args:
            token: String JWT recibido del header Authorization.

        Returns:
            Dict con el payload del token si es válido.
            None si el token está expirado, es inválido o malformado.
        """
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                cls._get_secret(),
                algorithms=[JWT_ALGORITHM],
            )
            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Token JWT rechazado: ha expirado.")
            return None

        except jwt.InvalidTokenError as exc:
            logger.warning("Token JWT inválido: %s", exc)
            return None

    @classmethod
    def encode_refresh(cls, user_id: str) -> str:
        """
        Genera un Refresh Token de larga duración (7 días).

        El refresh token sólo contiene el user_id y el claim 'type'
        para distinguirlo del access token en el servidor.

        Args:
            user_id: String del ObjectId del usuario.

        Returns:
            String del refresh token firmado.
        """
        return cls.encode(
            payload={"id": user_id, "type": "refresh"},
            ttl_hours=7 * 24,  # 7 días
        )


# --------------------------------------------------------------------------- #
# 2. PasswordService — Hash y Verificación con bcrypt
# --------------------------------------------------------------------------- #

class PasswordService:
    """
    Gestión segura de contraseñas usando bcrypt.

    bcrypt aplica un factor de costo (work factor) que hace que cada
    operación de hash tome ~0.1s, protegiéndose contra ataques de
    fuerza bruta aunque la base de datos sea comprometida.

    Uso:
        hashed = PasswordService.hash("mi_contraseña")  # str guardado en MongoDB
        ok     = PasswordService.verify("mi_contraseña", hashed)  # True/False
    """

    # Factor de costo bcrypt (12 es el estándar mínimo recomendado en 2024)
    BCRYPT_ROUNDS = 12

    @classmethod
    def hash(cls, plain_password: str) -> str:
        """
        Genera el hash bcrypt de una contraseña en texto plano.

        Args:
            plain_password: Contraseña original del usuario.

        Returns:
            Hash bcrypt como string (incluye salt y factor de costo).
        """
        if not plain_password:
            raise ValueError("La contraseña no puede estar vacía.")

        salt = bcrypt.gensalt(rounds=cls.BCRYPT_ROUNDS)
        hashed: bytes = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @classmethod
    def verify(cls, plain_password: str, hashed_password: str) -> bool:
        """
        Compara una contraseña en texto plano con su hash almacenado.

        Usa comparación en tiempo constante (bcrypt.checkpw) para evitar
        ataques de timing side-channel.

        Args:
            plain_password:   Contraseña ingresada por el usuario.
            hashed_password:  Hash almacenado en MongoDB.

        Returns:
            True si la contraseña coincide, False en cualquier otro caso.
        """
        if not plain_password or not hashed_password:
            return False
        try:
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Error al verificar contraseña: %s", exc)
            return False


# --------------------------------------------------------------------------- #
# 3. Decorador @jwt_required
# --------------------------------------------------------------------------- #

def jwt_required(
    view_func: Optional[Callable] = None,
    *,
    roles: Optional[list[str]] = None,
) -> Callable:
    """
    Decorador que protege una vista Django exigiendo un JWT válido.

    Uso básico (cualquier usuario autenticado):
        @jwt_required
        def mi_vista(request):
            user_id = request.user_payload["id"]
            ...

    Uso con restricción de roles:
        @jwt_required(roles=["admin"])
        def panel_admin(request):
            ...

    Flujo de validación:
        1. Extrae el header "Authorization: Bearer <token>".
        2. Decodifica y valida el JWT (firma + expiración).
        3. Inyecta `request.user_payload` con el dict del token.
        4. Si el decorador tiene 'roles', verifica que el rol del token
           esté en la lista permitida.
        5. Devuelve 401 con mensaje claro en cualquier fallo.

    Args:
        view_func: Vista Django a proteger (asignado automáticamente).
        roles:     Lista de roles permitidos (ej. ["admin", "operador"]).
                   Si es None, cualquier rol autenticado pasa.

    Returns:
        Vista decorada que retorna 401 si la autenticación falla.
    """
    # Soporte para uso con y sin paréntesis:
    # @jwt_required        → view_func recibe la función directamente
    # @jwt_required(roles=["admin"]) → view_func es None, se usa como factory
    def decorator(func: Callable) -> Callable:

        @functools.wraps(func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:

            # ── Paso 1: Extraer el token del header ─────────────────────── #
            auth_header: str = request.META.get(AUTH_HEADER, "")

            if not auth_header.startswith(BEARER_PREFIX):
                return JsonResponse(
                    {
                        "error": "Autenticación requerida.",
                        "detail": (
                            "Incluye el header 'Authorization: Bearer <token>'"
                            " en tu petición."
                        ),
                    },
                    status=401,
                )

            token: str = auth_header[len(BEARER_PREFIX):].strip()

            if not token:
                return JsonResponse(
                    {"error": "Token vacío.", "detail": "El token JWT no puede estar vacío."},
                    status=401,
                )

            # ── Paso 2: Decodificar y validar el token ───────────────────── #
            payload = JWTService.decode(token)

            if payload is None:
                # decode() ya registró el motivo exacto en el logger
                return JsonResponse(
                    {
                        "error": "Token inválido o expirado.",
                        "detail": (
                            "El token JWT ha expirado o su firma no es válida. "
                            "Inicia sesión nuevamente para obtener un token fresco."
                        ),
                    },
                    status=401,
                )

            # Rechazar refresh tokens usados como access tokens
            if payload.get("type") == "refresh":
                return JsonResponse(
                    {
                        "error": "Tipo de token incorrecto.",
                        "detail": "No puedes usar un refresh token para autenticarte.",
                    },
                    status=401,
                )

            # ── Paso 3: Verificar rol (si se especificaron roles) ────────── #
            if roles is not None:
                user_rol: str = payload.get("rol", "")
                if user_rol not in roles:
                    logger.warning(
                        "Acceso denegado: user_id=%s con rol='%s' intentó acceder "
                        "a un recurso restringido a roles=%s",
                        payload.get("id"),
                        user_rol,
                        roles,
                    )
                    return JsonResponse(
                        {
                            "error": "Acceso denegado.",
                            "detail": (
                                f"Tu rol '{user_rol}' no tiene permiso para este recurso. "
                                f"Se requiere uno de: {roles}."
                            ),
                        },
                        status=403,
                    )

            # ── Paso 4: Inyectar payload en el request ───────────────────── #
            # El payload contiene como mínimo: id, email, rol, iat, exp
            request.user_payload = payload  # type: ignore[attr-defined]

            logger.debug(
                "Acceso autorizado: user_id=%s, rol=%s → %s",
                payload.get("id"),
                payload.get("rol"),
                request.path,
            )

            return func(request, *args, **kwargs)

        return wrapper

    # Permite usar el decorador con o sin paréntesis
    if view_func is not None:
        # @jwt_required  (sin paréntesis)
        return decorator(view_func)

    # @jwt_required(roles=[...])  (con paréntesis)
    return decorator
