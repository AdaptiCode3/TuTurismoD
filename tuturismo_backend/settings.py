"""
Django settings for tuturismo_backend project.

Configured for Django 6.0 + PyMongo (sin ORM relacional).
Documentación: https://docs.djangoproject.com/en/6.0/ref/settings/
"""

from pathlib import Path
from dotenv import load_dotenv
import os

# ─── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Variables de Entorno ────────────────────────────────────────────────────
# Cargamos el archivo .env antes de leer cualquier variable.
# load_dotenv() no sobreescribe variables ya definidas en el entorno del SO,
# lo que permite que en producción (CI/CD, Docker) las variables del sistema
# tengan prioridad sobre el archivo .env.
load_dotenv(BASE_DIR / '.env')


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# ─── Seguridad ───────────────────────────────────────────────────────────────
# SECRET_KEY nunca debe estar hardcodeada. Se lee desde la variable de entorno.
# Si no está definida, lanzamos un error claro en lugar de arrancar con una
# clave insegura por defecto.
SECRET_KEY: str = os.environ['SECRET_KEY']

DEBUG: bool = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

# ALLOWED_HOSTS se define como lista separada por comas en el .env
ALLOWED_HOSTS: list[str] = [
    h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
]


# Application definition

INSTALLED_APPS: list[str] = [
    # Django internals (mantenemos staticfiles y messages para el admin si se usa)
    'django.contrib.staticfiles',
    # CORS — debe aparecer en INSTALLED_APPS para que Django lo reconozca
    'corsheaders',
    # Django REST Framework
    'rest_framework',
    # Apps del proyecto
    'core',
]

MIDDLEWARE: list[str] = [
    # CorsMiddleware DEBE estar lo más arriba posible, antes de cualquier
    # middleware que genere respuestas (ej. CommonMiddleware), para que las
    # peticiones OPTIONS (preflight) reciban las cabeceras CORS correctas.
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'tuturismo_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'tuturismo_backend.wsgi.application'


# ─── Base de Datos ───────────────────────────────────────────────────────────
# RESTRICCIÓN ARQUITECTÓNICA: Este proyecto usa PyMongo directamente.
# NO se usa el ORM relacional de Django. Por eso DATABASES se deja vacío.
# La conexión real se gestiona en core/database.py mediante MongoDBClient.
DATABASES: dict = {}

# ─── MongoDB (PyMongo) ───────────────────────────────────────────────────────
# Estas variables son leídas por core/database.py → MongoDBClient._connect()
MONGO_URI: str = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
MONGO_DB_NAME: str = os.getenv('MONGO_DB_NAME', 'tuturismo_db')


# ─── CORS ────────────────────────────────────────────────────────────────────
# Orígenes permitidos para peticiones cross-origin del frontend.
# Si estamos en desarrollo (DEBUG=True), permitimos todo para evitar bloqueos de CORS.
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOWED_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            'CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://localhost:5173'
        ).split(',')
        if origin.strip()
    ]

# Permite enviar cookies/credenciales en peticiones CORS (útil para sesiones)
CORS_ALLOW_CREDENTIALS: bool = True


# ─── Django REST Framework ───────────────────────────────────────────────────
# Solo JSON: desactivamos el BrowsableAPI renderer en producción.
# La autenticación/permisos los manejamos manualmente con @jwt_required
# (sin usar django.contrib.auth), por eso los dejamos vacíos aquí.
REST_FRAMEWORK: dict = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [],
    'DEFAULT_PERMISSION_CLASSES': [],
    'UNAUTHENTICATED_USER': None,
}


# ─── Internacionalización ────────────────────────────────────────────────────
LANGUAGE_CODE: str = 'es-mx'
TIME_ZONE: str = 'America/Mexico_City'
USE_I18N: bool = True
USE_TZ: bool = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
