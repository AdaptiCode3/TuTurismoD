"""
core/repositories/places.py
============================
Repositorio concreto para la colección de lugares turísticos.

Adapta la interfaz BaseRepository a la colección existente en MongoDB,
aplicando un mapeo defensivo (tolerante a esquemas flexibles) que convierte
los documentos BSON crudos en objetos PlaceDocument tipados antes de
que salgan de esta capa hacia las vistas o servicios.

RESTRICCIÓN DE SEGURIDAD: Este módulo NO ejecuta comandos DDL sobre la
base de datos (sin createCollection, sin schema validators, sin dropIndex).
Sólo operaciones de lectura/escritura sobre la colección existente.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from pymongo.errors import PyMongoError

from core.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Nombre de la colección en MongoDB
# Cambia este valor si la colección en tu Atlas se llama distinto
# (ej. "destinos", "turismo", "places", etc.)
# --------------------------------------------------------------------------- #
PLACES_COLLECTION_NAME = "lugars"


# --------------------------------------------------------------------------- #
# Modelo de datos Python — estructura canónica de un lugar turístico
# --------------------------------------------------------------------------- #

@dataclass
class PlaceDocument:
    """
    Representación tipada de un documento de la colección de lugares.

    Todos los campos usan valores por defecto (None / "") para tolerar
    documentos históricos que no cuenten con algún campo específico.
    Esto evita KeyError o AttributeError al procesar la colección existente.

    Campos:
        id          : ObjectId serializado como string hexadecimal.
        nombre      : Nombre del lugar turístico.
        municipio   : Municipio de Jalisco al que pertenece.
        categoria   : Categoría del lugar (Playa, Pueblo Mágico, etc.).
        descripcion : Descripción textual del atractivo.
        direccion   : Dirección o referencia geográfica (opcional).
        imagen_url  : URL de imagen representativa (opcional).
        coordenadas : Dict con {"lat": float, "lng": float} (opcional).
        activo      : Flag para soft-delete lógico (default True).
        tags        : Lista de etiquetas para búsqueda (opcional).
    """
    id: Optional[str] = None
    nombre: str = ""
    municipio: str = ""
    categoria: str = ""
    descripcion: str = ""
    direccion: str = ""
    imagen_url: str = ""
    coordenadas: Optional[dict[str, float]] = None
    activo: bool = True
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serializa el dataclass a dict plano (útil para JsonResponse)."""
        return asdict(self)

    def __repr__(self) -> str:
        return f"<PlaceDocument id={self.id!r} nombre={self.nombre!r}>"


# --------------------------------------------------------------------------- #
# Repositorio concreto
# --------------------------------------------------------------------------- #

class PlaceRepository(BaseRepository[PlaceDocument]):
    """
    Repositorio para la colección de lugares turísticos existente en MongoDB.

    Hereda todas las operaciones CRUD de BaseRepository y especializa:
      - _map_document(): transforma BSON → PlaceDocument de forma defensiva.
      - Métodos de consulta específicos del dominio turístico.

    Uso básico:
        repo = PlaceRepository()
        places = repo.get_all()
        place  = repo.get_by_id("64a1f3c8e4b0a1b2c3d4e5f6")
    """

    def __init__(self) -> None:
        """Inicializa conectándose a la colección de lugares existente."""
        super().__init__(PLACES_COLLECTION_NAME)

    # ------------------------------------------------------------------ #
    # Implementación del mapeo BSON → PlaceDocument
    # ------------------------------------------------------------------ #

    def _map_document(self, document: dict[str, Any]) -> PlaceDocument:
        """
        Convierte un documento MongoDB crudo en un PlaceDocument tipado.

        Estrategia de tolerancia a fallos:
          - Usa .get(campo, valor_default) en TODOS los campos para no
            lanzar KeyError si el documento histórico no los tiene.
          - Castea cada valor al tipo esperado para evitar errores de tipo
            en capas superiores (str(), bool(), list(), etc.).
          - Captura cualquier excepción inesperada y devuelve un
            PlaceDocument vacío con el id conservado para trazabilidad.

        Args:
            document: Dict con '_id' ya serializado a 'id' (string),
                      tal como lo entrega BaseRepository._serialize_id().

        Returns:
            PlaceDocument con campos saneados y con valores por defecto
            para los campos que no existan en el documento original.
        """
        doc_id = document.get("id")

        try:
            # --- Coordenadas: validación de estructura anidada ---
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

            if not coordenadas:
                raw_coords = document.get("coordenadas") or document.get("coordinates")
                if isinstance(raw_coords, dict):
                    try:
                        coordenadas = {
                            "lat": float(raw_coords.get("lat", 0.0)),
                            "lng": float(raw_coords.get("lng", raw_coords.get("lon", 0.0))),
                        }
                    except (TypeError, ValueError):
                        logger.warning(
                            "Coordenadas malformadas en documento id=%s, ignorando.", doc_id
                        )
                        coordenadas = None

            # --- Tags: acepta lista o string separado por comas ---
            raw_tags = document.get("tags", [])
            if isinstance(raw_tags, str):
                tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
            elif isinstance(raw_tags, list):
                tags = [str(t) for t in raw_tags]
            else:
                tags = []

            return PlaceDocument(
                id=doc_id,
                nombre=str(document.get("nombre") or document.get("name") or ""),
                municipio=str(document.get("municipio") or document.get("municipality") or ""),
                categoria=str(document.get("categoria") or document.get("category") or ""),
                descripcion=str(
                    document.get("descripcion")
                    or document.get("description")
                    or ""
                ),
                direccion=str(
                    document.get("direccion")
                    or document.get("address")
                    or document.get("direccion_completa")
                    or ""
                ),
                imagen_url=self._parse_imagen(document),
                coordenadas=coordenadas,
                activo=bool(document.get("activo", True)),
                tags=tags,
            )

        except Exception as exc:  # noqa: BLE001
            # Captura defensiva: nunca debe romper el listado completo
            # por un documento corrupto individual.
            logger.error(
                "Error al mapear documento id=%s en PlaceRepository: %s",
                doc_id,
                exc,
            )
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

    # ------------------------------------------------------------------ #
    # Consultas específicas del dominio turístico
    # ------------------------------------------------------------------ #

    def get_by_municipio(self, municipio: str) -> list[PlaceDocument]:
        """
        Filtra lugares por municipio (case-insensitive con regex).

        Args:
            municipio: Nombre del municipio a filtrar.

        Returns:
            Lista de PlaceDocument del municipio indicado.
        """
        import re

        query = {"$or": [
            {"municipio": {"$regex": re.escape(municipio), "$options": "i"}},
            {"municipality": {"$regex": re.escape(municipio), "$options": "i"}},
        ]}
        return self.get_all(query=query)

    def get_by_categoria(self, categoria: str) -> list[PlaceDocument]:
        """
        Filtra lugares por categoría turística (case-insensitive).

        Args:
            categoria: Categoría a filtrar (ej. "Playas", "Pueblos Mágicos").

        Returns:
            Lista de PlaceDocument de la categoría indicada.
        """
        import re

        query = {"$or": [
            {"categoria": {"$regex": re.escape(categoria), "$options": "i"}},
            {"category": {"$regex": re.escape(categoria), "$options": "i"}},
        ]}
        return self.get_all(query=query)

    def search(self, text: str) -> list[PlaceDocument]:
        """
        Búsqueda de texto libre en nombre, municipio y descripción.

        Usa regex para compatibilidad con colecciones sin índice de texto
        completo (text index). Si tu colección tiene un índice de texto,
        considera reemplazar por $text / $search para mejor rendimiento.

        Args:
            text: Término de búsqueda libre.

        Returns:
            Lista de PlaceDocument que coinciden con el texto buscado.
        """
        import re

        pattern = {"$regex": re.escape(text), "$options": "i"}
        query = {"$or": [
            {"nombre": pattern},
            {"name": pattern},
            {"municipio": pattern},
            {"municipality": pattern},
            {"descripcion": pattern},
            {"description": pattern},
            {"tags": pattern},
        ]}
        return self.get_all(query=query)

    def get_activos(self, limit: int = 100) -> list[PlaceDocument]:
        """
        Devuelve sólo los lugares marcados como activos.

        Args:
            limit: Máximo de resultados (default 100).

        Returns:
            Lista de PlaceDocument activos, ordenados por nombre.
        """
        return self.get_all(
            query={"activo": {"$ne": False}},
            limit=limit,
            sort_by="nombre",
        )

    def get_categorias_disponibles(self) -> list[str]:
        """
        Obtiene la lista de categorías únicas presentes en la colección.

        Usa distinct() de PyMongo para eficiencia (sin cargar documentos
        completos). Agrega las claves alternativas "category" y "categoria".

        Returns:
            Lista de strings con categorías únicas, sin duplicados.
        """
        try:
            cats_es: list[str] = self._collection.distinct("categoria") or []
            cats_en: list[str] = self._collection.distinct("category") or []
            # Combinar y deduplicar manteniendo mayúsculas originales
            seen: set[str] = set()
            result: list[str] = []
            for cat in cats_es + cats_en:
                if cat and isinstance(cat, str) and cat.lower() not in seen:
                    seen.add(cat.lower())
                    result.append(cat)
            return sorted(result)

        except PyMongoError as exc:
            logger.error("Error en get_categorias_disponibles(): %s", exc)
            return []

    def get_municipios_disponibles(self) -> list[str]:
        """
        Obtiene la lista de municipios únicos presentes en la colección.

        Returns:
            Lista de strings con municipios únicos, ordenados alfabéticamente.
        """
        try:
            munis_es: list[str] = self._collection.distinct("municipio") or []
            munis_en: list[str] = self._collection.distinct("municipality") or []
            seen: set[str] = set()
            result: list[str] = []
            for muni in munis_es + munis_en:
                if muni and isinstance(muni, str) and muni.lower() not in seen:
                    seen.add(muni.lower())
                    result.append(muni)
            return sorted(result)

        except PyMongoError as exc:
            logger.error("Error en get_municipios_disponibles(): %s", exc)
            return []

    def get_nearby(
        self,
        lat: float,
        lng: float,
        max_distance: int = 10_000,
        limit: int = 20,
    ) -> list[PlaceDocument]:
        """
        Devuelve lugares ordenados por cercanía a las coordenadas dadas.

        Requiere que la colección tenga un índice 2dsphere sobre el campo
        'ubicacion' (formato GeoJSON Point). Los resultados llegan ya
        ordenados de más cercano a más lejano por MongoDB.

        Estructura esperada del campo 'ubicacion' en MongoDB:
            { "type": "Point", "coordinates": [lng, lat] }
            ⚠️ MongoDB usa [longitud, latitud], NO [latitud, longitud].

        Args:
            lat:          Latitud del punto de referencia (decimal).
            lng:          Longitud del punto de referencia (decimal).
            max_distance: Radio máximo en metros (default 10 km).
            limit:        Máximo de resultados (default 20).

        Returns:
            Lista de PlaceDocument ordenados por distancia ascendente.
            Lista vacía si no hay resultados o si falla la consulta.
        """
        try:
            cursor = self._collection.find(
                {
                    "ubicacion": {
                        "$near": {
                            "$geometry": {
                                "type": "Point",
                                # ⚠️ GeoJSON: [longitud, latitud]
                                "coordinates": [lng, lat],
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
