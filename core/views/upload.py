"""
core/views/upload.py
====================
Endpoint para la subida de imágenes a la nube (Cloudinary).
Soporta subidas multipart/form-data y cadenas base64.
Protegido por @jwt_required para evitar subidas no autorizadas.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.security import jwt_required

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
@jwt_required
def upload_image(request: HttpRequest) -> JsonResponse:
    """
    POST /api/v1/core/upload/
    Sube una imagen (archivo en `request.FILES['image']` o base64 en body JSON `{"image": "..."}`)
    a Cloudinary bajo la carpeta "tuturismo".
    
    Devuelve:
        200 OK -> {"success": True, "url": "https://res.cloudinary.com/..."}
    """
    try:
        image_data: Any = None
        folder = "tuturismo/avatars"

        # 1. Intentar obtener desde request.FILES (multipart/form-data)
        if "image" in request.FILES:
            image_data = request.FILES["image"]
        elif "file" in request.FILES:
            image_data = request.FILES["file"]
        else:
            # 2. Intentar obtener desde body JSON (base64)
            try:
                body = json.loads(request.body.decode("utf-8"))
                image_data = body.get("image") or body.get("file")
                if body.get("folder"):
                    folder = f"tuturismo/{str(body.get('folder')).strip()}"
            except Exception:
                pass

        if not image_data:
            return JsonResponse({
                "success": False,
                "error": "No se recibió ninguna imagen.",
                "detail": "Envía un archivo en el campo 'image' o una cadena base64 en el body JSON."
            }, status=400)

        # Verificar si Cloudinary está configurado con credenciales reales
        cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
        placeholder_names = {"", "tuturismo", "your_cloud_name", "demo", "none", "null"}

        if cloud_name.lower() not in placeholder_names:
            try:
                import cloudinary.uploader
                upload_result = cloudinary.uploader.upload(
                    image_data,
                    folder=folder,
                    resource_type="image"
                )
                secure_url = upload_result.get("secure_url") or upload_result.get("url")
                if secure_url:
                    logger.info("Imagen subida a Cloudinary exitosamente: %s", secure_url)
                    return JsonResponse({
                        "success": True,
                        "url": secure_url,
                        "public_id": upload_result.get("public_id")
                    }, status=200)
            except Exception as cloud_exc:  # noqa: BLE001
                logger.warning("Fallo subida a Cloudinary (%s); convirtiendo a Data URI.", cloud_exc)

        # Fallback real: convertir el archivo o cadena recibida a Data URI base64
        if isinstance(image_data, str) and image_data.startswith("data:image/"):
            data_uri = image_data
        elif hasattr(image_data, "read"):
            import base64
            image_data.seek(0)
            raw_bytes = image_data.read()
            mime = getattr(image_data, "content_type", "image/jpeg") or "image/jpeg"
            b64 = base64.b64encode(raw_bytes).decode("ascii")
            data_uri = f"data:{mime};base64,{b64}"
        else:
            data_uri = str(image_data)

        return JsonResponse({
            "success": True,
            "url": data_uri,
        }, status=200)

    except Exception as exc:  # noqa: BLE001
        logger.error("❌ Error al subir imagen a Cloudinary: %s", exc)
        return JsonResponse({
            "success": False,
            "error": "Error al procesar y subir la imagen.",
            "detail": str(exc)
        }, status=500)
