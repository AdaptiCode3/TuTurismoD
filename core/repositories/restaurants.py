"""
core/repositories/restaurants.py
==================================
Repositorio concreto para la colección de restaurantes.

Conecta con la colección 'restaurantes' existente en MongoDB y aplica
un mapeo defensivo que convierte documentos BSON en objetos RestaurantDocument
tipados, tolerando esquemas variables en documentos históricos.

Incluye consulta geoespacial $near sobre el campo 'ubicacion' (índice 2dsphere).

RESTRICCIÓN DE SEGURIDAD: Sin DDL. Sólo lectura/escritura sobre la colección
existente. Nunca createCollection, dropIndex ni schema validators.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from pymongo.errors import PyMongoError

from core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Nombre exacto de la colección en MongoDB
# --------------------------------------------------------------------------- #
RESTAURANTS_COLLECTION_NAME = "restaurantes"


# --------------------------------------------------------------------------- #
# Modelo de datos Python — estructura canónica de un restaurante
# --------------------------------------------------------------------------- #

@dataclass
class RestaurantDocument:
    """
    Representación tipada de un documento de la colección 'restaurantes'.

    Todos los campos usan valores por defecto para tolerar documentos
    históricos con estructura variable. Ningún campo es obligatorio en
    el mapeo para no romper listados ante registros incompletos.

    Campos:
        id           : ObjectId serializado como string hexadecimal.
        nombre       : Nombre del restaurante.
        municipio    : Municipio de Jalisco donde está ubicado.
        categoria    : Tipo de cocina / categoría (mariscos, tacos, etc.).
        descripcion  : Descripción del establecimiento.
        direccion    : Dirección física.
        telefono     : Número de contacto (opcional).
        horario      : Horario de atención (opcional).
        precio_rango : Rango de precios: "$", "$$", "$$$" (opcional).
        imagen_url   : URL de imagen representativa (opcional).
        coordenadas  : Dict {"lat": float, "lng": float} extraído del GeoJSON.
        calificacion : Calificación promedio (0.0 – 5.0, opcional).
        activo       : Flag para soft-delete lógico (default True).
        tags         : Lista de etiquetas para búsqueda.
    """
    id: Optional[str] = None
    nombre: str = ""
    municipio: str = ""
    categoria: str = ""
    descripcion: str = ""
    direccion: str = ""
    telefono: str = ""
    horario: str = ""
    precio_rango: str = ""
    imagen_url: str = ""
    coordenadas: Optional[dict[str, float]] = None
    calificacion: Optional[float] = None
    activo: bool = True
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serializa el dataclass a dict plano."""
        return asdict(self)

    def __repr__(self) -> str:
        return f"<RestaurantDocument id={self.id!r} nombre={self.nombre!r}>"


# --------------------------------------------------------------------------- #
# Repositorio concreto
# --------------------------------------------------------------------------- #

class RestaurantRepository(BaseRepository[RestaurantDocument]):
    """
    Repositorio para la colección 'restaurantes' existente en MongoDB.

    Hereda CRUD de BaseRepository y especializa:
      - _map_document(): BSON → RestaurantDocument (esquema flexible).
      - get_nearby(): Consulta geoespacial $near sobre índice 2dsphere.
      - Filtros de dominio: por municipio, categoría, rango de precio.

    Uso básico:
        repo = RestaurantRepository()
        restaurants = repo.get_all(limit=50)
        nearby = repo.get_nearby(lat=20.67, lng=-103.34, max_distance=2000)
    """

    def __init__(self) -> None:
        """Inicializa conectándose a la colección 'restaurantes' existente."""
        super().__init__(RESTAURANTS_COLLECTION_NAME)

    # ------------------------------------------------------------------ #
    # Implementación del mapeo BSON → RestaurantDocument
    # ------------------------------------------------------------------ #

    def _map_document(self, document: dict[str, Any]) -> RestaurantDocument:
        """
        Convierte un documento MongoDB crudo en un RestaurantDocument tipado.

        Estrategia de tolerancia a fallos:
          - .get() con default en todos los campos.
          - Extrae coordenadas del campo GeoJSON 'ubicacion' si existe,
            o del campo plano 'coordenadas' como fallback.
          - Captura cualquier excepción individual sin romper el listado.

        Args:
            document: Dict con '_id' serializado a 'id' por BaseRepository.
        """
        doc_id = document.get("id")

        try:
            # ── Coordenadas: desde GeoJSON 'ubicacion' o campo plano ── #
            coordenadas: Optional[dict[str, float]] = None

            raw_ubicacion = document.get("ubicacion")
            if isinstance(raw_ubicacion, dict) and raw_ubicacion.get("type") == "Point":
                coords = raw_ubicacion.get("coordinates", [])
                if isinstance(coords, (list, tuple)) and len(coords) == 2:
                    try:
                        # GeoJSON: [longitud, latitud] → invertimos para UI
                        coordenadas = {
                            "lat": float(coords[1]),
                            "lng": float(coords[0]),
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

            # ── Tags ── #
            raw_tags = document.get("tags", [])
            if isinstance(raw_tags, str):
                tags: list[str] = [t.strip() for t in raw_tags.split(",") if t.strip()]
            elif isinstance(raw_tags, list):
                tags = [str(t) for t in raw_tags]
            else:
                tags = []

            # ── Calificación ── #
            raw_cal = document.get("calificacion") or document.get("rating")
            calificacion: Optional[float] = None
            if raw_cal is not None:
                try:
                    calificacion = round(float(raw_cal), 1)
                except (TypeError, ValueError):
                    pass

            return RestaurantDocument(
                id=doc_id,
                nombre=str(
                    document.get("nombre") or document.get("name") or ""
                ),
                municipio=str(
                    document.get("municipio") or document.get("municipality") or ""
                ),
                categoria=str(
                    document.get("categoria") or document.get("category") or ""
                ),
                descripcion=str(
                    document.get("descripcion") or document.get("description") or ""
                ),
                direccion=str(
                    document.get("direccion") or document.get("address") or ""
                ),
                telefono=str(document.get("telefono") or document.get("phone") or ""),
                horario=str(document.get("horario") or document.get("hours") or ""),
                precio_rango=str(
                    document.get("precio_rango") or document.get("price_range") or ""
                ),
                imagen_url=str(
                    document.get("imagen_url")
                    or document.get("image_url")
                    or document.get("imagen")
                    or ""
                ),
                coordenadas=coordenadas,
                calificacion=calificacion,
                activo=bool(document.get("activo", True)),
                tags=tags,
            )

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Error al mapear RestaurantDocument id=%s: %s", doc_id, exc
            )
            return RestaurantDocument(id=doc_id)

    # ------------------------------------------------------------------ #
    # Consulta geoespacial
    # ------------------------------------------------------------------ #

    def get_nearby(
        self,
        lat: float,
        lng: float,
        max_distance: int = 5_000,
        limit: int = 20,
    ) -> list[RestaurantDocument]:
        """
        Devuelve restaurantes ordenados por cercanía a las coordenadas dadas.

        Requiere índice 2dsphere sobre el campo 'ubicacion' en la colección.
        Los resultados se entregan ya ordenados de más cercano a más lejano.

        Estructura esperada del campo 'ubicacion' en MongoDB:
            { "type": "Point", "coordinates": [lng, lat] }
            ⚠️ MongoDB usa [longitud, latitud], NO [latitud, longitud].

        Args:
            lat:          Latitud del punto de referencia (decimal).
            lng:          Longitud del punto de referencia (decimal).
            max_distance: Radio máximo en metros (default 5 km).
            limit:        Máximo de resultados (default 20).

        Returns:
            Lista de RestaurantDocument ordenados por distancia ascendente.
        """
        try:
            cursor = self._collection.find(
                {
                    "ubicacion": {
                        "$near": {
                            "$geometry": {
                                "type": "Point",
                                "coordinates": [lng, lat],   # ⚠️ GeoJSON: [lng, lat]
                            },
                            "$maxDistance": max_distance,
                        }
                    }
                }
            ).limit(limit)

            return [
                self._map_document(self._serialize_id(doc))
                for doc in cursor
            ]

        except PyMongoError as exc:
            logger.error(
                "Error en get_nearby(lat=%s, lng=%s, max_distance=%s): %s",
                lat, lng, max_distance, exc,
            )
            return []

    # ------------------------------------------------------------------ #
    # Consultas de dominio
    # ------------------------------------------------------------------ #

    def get_by_municipio(self, municipio: str) -> list[RestaurantDocument]:
        """Filtra restaurantes por municipio (case-insensitive)."""
        import re
        pattern = {"$regex": re.escape(municipio), "$options": "i"}
        return self.get_all(query={"$or": [
            {"municipio": pattern}, {"municipality": pattern},
        ]})

    def get_by_categoria(self, categoria: str) -> list[RestaurantDocument]:
        """Filtra restaurantes por categoría (case-insensitive)."""
        import re
        pattern = {"$regex": re.escape(categoria), "$options": "i"}
        return self.get_all(query={"$or": [
            {"categoria": pattern}, {"category": pattern},
        ]})

    def get_activos(self, limit: int = 100) -> list[RestaurantDocument]:
        """Devuelve sólo los restaurantes activos, ordenados por nombre."""
        return self.get_all(
            query={"activo": {"$ne": False}},
            limit=limit,
            sort_by="nombre",
        )
