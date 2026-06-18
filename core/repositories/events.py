"""
core/repositories/events.py
============================
Repositorio para la colección 'eventos' usando PyMongo nativo.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

EVENTS_COLLECTION_NAME = "eventos"


@dataclass
class EventDocument:
    """Representación tipada de un documento de la colección eventos."""
    id: Optional[str] = None
    nombre: str = ""
    descripcion: str = ""
    categoria: str = ""
    municipio: str = ""
    fecha_inicio: str = ""
    fecha_fin: str = ""
    imagen_url: str = ""
    activo: bool = True
    coordenadas: Optional[dict[str, float]] = None
    tags: list[str] = field(default_factory=list)


class EventRepository(BaseRepository[EventDocument]):
    def __init__(self) -> None:
        super().__init__(EVENTS_COLLECTION_NAME)

    def _map_document(self, document: dict[str, Any]) -> EventDocument:
        doc_id = document.get("id")
        try:
            coordenadas: Optional[dict[str, float]] = None
            raw_ubicacion = document.get("ubicacion")
            if isinstance(raw_ubicacion, dict):
                raw_coords_list = raw_ubicacion.get("coordinates")
                if isinstance(raw_coords_list, list) and len(raw_coords_list) >= 2:
                    try:
                        coordenadas = {
                            "lng": float(raw_coords_list[0]),
                            "lat": float(raw_coords_list[1]),
                        }
                    except (TypeError, ValueError):
                        pass

            # Tags: acepta lista o string separado por comas
            raw_tags = document.get("tags", [])
            if isinstance(raw_tags, str):
                tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
            elif isinstance(raw_tags, list):
                tags = [str(t) for t in raw_tags]
            else:
                tags = []

            return EventDocument(
                id=doc_id,
                nombre=str(document.get("nombre") or document.get("name") or ""),
                descripcion=str(document.get("descripcion") or document.get("description") or ""),
                categoria=str(document.get("categoria") or document.get("category") or ""),
                municipio=str(document.get("municipio") or document.get("municipality") or ""),
                # Acepta fecha_inicio, fecha, date o date_start
                fecha_inicio=str(
                    document.get("fecha_inicio")
                    or document.get("fecha")
                    or document.get("date")
                    or document.get("date_start")
                    or ""
                ),
                fecha_fin=str(
                    document.get("fecha_fin")
                    or document.get("date_end")
                    or ""
                ),
                imagen_url=self._parse_imagen(document),
                activo=bool(document.get("activo", True)),
                coordenadas=coordenadas,
                tags=tags,
            )

        except Exception as exc:  # noqa: BLE001
            logger.error("Error al mapear evento id=%s: %s", doc_id, exc)
            return EventDocument(id=doc_id)

    def _parse_imagen(self, document: dict[str, Any]) -> str:
        raw_imagen = str(document.get("imagen_url") or document.get("image_url") or document.get("imagen") or "")
        if raw_imagen:
            return raw_imagen
        raw_imagenes = document.get("imagenes")
        if isinstance(raw_imagenes, str):
            import json
            try:
                lista_img = json.loads(raw_imagenes)
                if isinstance(lista_img, list) and len(lista_img) > 0:
                    return str(lista_img[0])
            except json.JSONDecodeError:
                pass
        return ""
