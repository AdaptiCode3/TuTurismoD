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
from core.repositories.geo_resolver import resolve_municipio

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

            if coordenadas is None:
                raw_coords = document.get("coordenadas") or document.get("coordinates")
                if isinstance(raw_coords, dict):
                    try:
                        coordenadas = {
                            "lat": float(raw_coords.get("lat", 0.0)),
                            "lng": float(raw_coords.get("lng", raw_coords.get("lon", 0.0))),
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

            nombre_clean = str(document.get("nombre") or document.get("name") or "")
            desc_clean = str(document.get("descripcion") or document.get("description") or "")
            resolved_muni = resolve_municipio(
                existing_value=document.get("municipio") or document.get("municipality"),
                coordenadas=coordenadas,
                direccion="",
                nombre=nombre_clean,
                descripcion=desc_clean,
            )

            return EventDocument(
                id=doc_id,
                nombre=nombre_clean,
                descripcion=desc_clean,
                categoria=str(document.get("categoria") or document.get("category") or ""),
                municipio=resolved_muni,
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

    def create_event(self, data: dict[str, Any]) -> Optional[EventDocument]:
        """Inserta un nuevo evento. Devuelve el documento creado o None."""
        from datetime import datetime, timezone
        data.setdefault("activo", True)
        data.setdefault("created_at", datetime.now(tz=timezone.utc).isoformat())
        new_id = self.insert(data)
        return self.get_by_id(new_id) if new_id else None

    def update_event(self, event_id: str, data: dict[str, Any]) -> Optional[EventDocument]:
        """Actualiza campos de un evento. Devuelve el documento actualizado o None."""
        protected = {"_id", "id", "created_at"}
        updates = {k: v for k, v in data.items() if k not in protected}
        if not updates:
            return self.get_by_id(event_id)
        self.update(event_id, updates)
        return self.get_by_id(event_id)

    def delete_event(self, event_id: str) -> bool:
        """Soft-delete: marca activo=False."""
        return self.update(event_id, {"activo": False})

