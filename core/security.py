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
import time
import threading
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
        
        return cls.encode(
            payload={"id": user_id, "type": "refresh"},
            ttl_hours=7 * 24,  # 7 días
        )


# --------------------------------------------------------------------------- #
# 2. PasswordService — Hash y Verificación con bcrypt
# --------------------------------------------------------------------------- #

class PasswordService:
    

    # Factor de costo bcrypt (12 es el estándar mínimo recomendado en 2024)
    BCRYPT_ROUNDS = 12

    @classmethod
    def hash(cls, plain_password: str) -> str:
        
        if not plain_password:
            raise ValueError("La contraseña no puede estar vacía.")

        salt = bcrypt.gensalt(rounds=cls.BCRYPT_ROUNDS)
        hashed: bytes = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @classmethod
    def verify(cls, plain_password: str, hashed_password: str) -> bool:
       
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


# --------------------------------------------------------------------------- #
# 4. Rate Limiter (Protección Anti-Fuerza Bruta)
# --------------------------------------------------------------------------- #

_RATE_LIMIT_CACHE: dict[str, list[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()


def rate_limit(max_requests: int = 5, window_seconds: int = 60) -> Callable:
    """
    Decorador para limitar peticiones por IP en endpoints sensibles (ej. login/register).
    Devuelve 429 Too Many Requests si se excede el límite en la ventana de tiempo.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
            # Obtener IP real del cliente considerando proxys/Cloudflare/Render
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                ip = x_forwarded_for.split(",")[0].strip()
            else:
                ip = request.META.get("REMOTE_ADDR", "unknown_ip")

            cache_key = f"{func.__name__}:{ip}"
            now = time.time()

            with _RATE_LIMIT_LOCK:
                # Limpiar timestamps expirados de esta clave
                timestamps = _RATE_LIMIT_CACHE.get(cache_key, [])
                valid_timestamps = [t for t in timestamps if now - t < window_seconds]

                if len(valid_timestamps) >= max_requests:
                    logger.warning("🚫 Rate limit excedido para IP %s en endpoint %s", ip, func.__name__)
                    return JsonResponse({
                        "error": "Demasiados intentos.",
                        "detail": f"Has superado el límite de {max_requests} intentos permitidos. Por favor, espera unos segundos e inténtalo de nuevo."
                    }, status=429)

                valid_timestamps.append(now)
                _RATE_LIMIT_CACHE[cache_key] = valid_timestamps

            return func(request, *args, **kwargs)
        return wrapper
    return decorator

