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
from core.repositories.geo_resolver import resolve_municipio

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
    rating_promedio: Optional[float] = None
    calificacion: Optional[float] = None
    reviews_count: int = 0

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

            # --- Calificación y Reseñas ---
            raw_rating = (
                document.get("rating_promedio")
                if document.get("rating_promedio") is not None
                else (document.get("rating") if document.get("rating") is not None else document.get("calificacion"))
            )
            rating_prom = None
            if raw_rating is not None and str(raw_rating).strip() != "":
                try:
                    rating_prom = float(raw_rating)
                except (ValueError, TypeError):
                    pass

            raw_reviews = (
                document.get("reviews_count")
                or document.get("num_reviews")
                or document.get("calificaciones_count")
                or 0
            )
            try:
                rev_count = int(raw_reviews)
            except (ValueError, TypeError):
                rev_count = 0

            nombre_clean = str(document.get("nombre") or document.get("name") or "")
            dir_clean = str(
                document.get("direccion")
                or document.get("address")
                or document.get("direccion_completa")
                or ""
            )
            desc_clean = str(document.get("descripcion") or document.get("description") or "")
            resolved_muni = resolve_municipio(
                existing_value=document.get("municipio") or document.get("municipality"),
                coordenadas=coordenadas,
                direccion=dir_clean,
                nombre=nombre_clean,
                descripcion=desc_clean,
            )

            return PlaceDocument(
                id=doc_id,
                nombre=nombre_clean,
                municipio=resolved_muni,
                categoria=str(document.get("categoria") or document.get("category") or ""),
                descripcion=desc_clean,
                direccion=dir_clean,
                imagen_url=self._parse_imagen(document),
                coordenadas=coordenadas,
                activo=bool(document.get("activo", True)),
                tags=tags,
                rating_promedio=rating_prom,
                calificacion=rating_prom,
                reviews_count=rev_count,
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

    # ------------------------------------------------------------------ #
    # Operaciones de escritura (admin)
    # ------------------------------------------------------------------ #

    def create_place(self, data: dict[str, Any]) -> Optional[PlaceDocument]:
        """Inserta un nuevo lugar. Devuelve el documento creado o None."""
        from datetime import datetime, timezone
        data.setdefault("activo", True)
        data.setdefault("created_at", datetime.now(tz=timezone.utc).isoformat())
        new_id = self.insert(data)
        return self.get_by_id(new_id) if new_id else None

    def update_place(self, place_id: str, data: dict[str, Any]) -> Optional[PlaceDocument]:
        """Actualiza campos de un lugar. Devuelve el documento actualizado o None."""
        protected = {"_id", "id", "created_at"}
        updates = {k: v for k, v in data.items() if k not in protected}
        if not updates:
            return self.get_by_id(place_id)
        self.update(place_id, updates)
        return self.get_by_id(place_id)

    def delete_place(self, place_id: str) -> bool:
        """Soft-delete: marca activo=False. Devuelve True si tuvo efecto."""
        return self.update(place_id, {"activo": False})

    def get_top_rated(self, limit: int = 5) -> list[PlaceDocument]:
        """
        Devuelve los mejores lugares turísticos utilizando el Modelo de Puntuación Bayesiana Ponderada.
        Fórmula Bayesiana:
            WR = (v / (v + m)) * R + (m / (v + m)) * C
        Donde:
            v = reviews_count (o 1 como base mínima para lugares con calificación)
            m = parámetro de prior bayesiano (ej. 3 reseñas mínimas)
            R = rating_promedio del lugar
            C = calificación media global del catálogo (prior mean)
        """
        all_places = self.get_all()
        # Filtrar lugares con calificación o asignar calificación media para ranking
        rated_places = []
        ratings_sum = 0.0
        count_rated = 0

        for p in all_places:
            if p.rating_promedio is not None and p.rating_promedio > 0:
                ratings_sum += p.rating_promedio
                count_rated += 1

        C = (ratings_sum / count_rated) if count_rated > 0 else 4.0
        m = 3.0  # prior

        places_with_score = []
        for p in all_places:
            R = p.rating_promedio if (p.rating_promedio is not None and p.rating_promedio > 0) else 3.8
            v = float(p.reviews_count) if p.reviews_count > 0 else (1.0 if p.rating_promedio else 0.5)
            # Puntuación Bayesiana WR
            wr = (v / (v + m)) * R + (m / (v + m)) * C
            places_with_score.append((wr, p))

        # Ordenar descendente por puntuación WR
        places_with_score.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in places_with_score[:limit]]

    def get_spatial_density_clusters(self) -> list[dict[str, Any]]:
        """
        Agrega la densidad territorial de lugares, restaurantes y eventos usando
        el algoritmo DBSCAN para descubrir verdaderos Corredores Turísticos.
        """
        from core.repositories.restaurants import RestaurantRepository
        from core.repositories.events import EventRepository
        from core.ml.spatial_clusterer import DBSCANClusterer

        all_places = self.get_all()
        
        try:
            all_restaurants = RestaurantRepository().get_all()
        except Exception:
            all_restaurants = []

        try:
            all_events = EventRepository().get_all()
        except Exception:
            all_events = []

        resources = []
        for p in all_places:
            if p.coordenadas and "lat" in p.coordenadas and "lng" in p.coordenadas:
                resources.append({
                    "type": "place",
                    "lat": p.coordenadas["lat"],
                    "lng": p.coordenadas["lng"],
                    "rating": p.rating_promedio,
                    "municipio": p.municipio
                })
        for r in all_restaurants:
            if r.coordenadas and "lat" in r.coordenadas and "lng" in r.coordenadas:
                resources.append({
                    "type": "restaurant",
                    "lat": r.coordenadas["lat"],
                    "lng": r.coordenadas["lng"],
                    "rating": r.calificacion,
                    "municipio": r.municipio
                })
        for e in all_events:
            if e.coordenadas and "lat" in e.coordenadas and "lng" in e.coordenadas:
                resources.append({
                    "type": "event",
                    "lat": e.coordenadas["lat"],
                    "lng": e.coordenadas["lng"],
                    "rating": None,
                    "municipio": e.municipio
                })

        clusterer = DBSCANClusterer(eps_km=3.0, min_samples=3)
        clusters_data = clusterer.cluster_resources(resources)
        result = []
        if not clusters_data:
            return result
        max_heat = max((c["heat_score"] for c in clusters_data.values()), default=1.0)
        if max_heat <= 0: max_heat = 1.0
        for name, data in clusters_data.items():
            lat, lng = data["coordenadas_centro"]
            normalized_heat = round(data["heat_score"] / max_heat, 3)
            result.append({
                "municipio": name,
                "total_recursos": data["total_recursos"],
                "coordenadas_centro": {"lat": round(lat, 6), "lng": round(lng, 6)},
                "desglose": data["desglose"],
                "rating_promedio": data["rating_promedio"],
                "heat_score": normalized_heat,
            })
        result.sort(key=lambda x: x["total_recursos"], reverse=True)
        return result

    def get_spatial_density_by_municipio(self) -> list[dict[str, Any]]:
        """
        Agrega la densidad y concentración territorial de lugares, restaurantes y eventos
        por municipio para el mapa territorial coroplético (estilo Power BI).
        """
        from core.repositories.restaurants import RestaurantRepository
        from core.repositories.events import EventRepository

        all_places = self.get_all()
        
        try:
            all_restaurants = RestaurantRepository().get_all()
        except Exception:
            all_restaurants = []

        try:
            all_events = EventRepository().get_all()
        except Exception:
            all_events = []

        municipios_data: dict[str, dict[str, Any]] = {}

        def get_or_create_muni(muni_name: str):
            name = (muni_name or "Guadalajara").strip().title()
            if not name or name in ("", "None", "Jalisco", "México", "Mexico"):
                name = "Guadalajara"
            if name not in municipios_data:
                municipios_data[name] = {
                    "municipio": name,
                    "total_recursos": 0,
                    "desglose": {"lugares": 0, "restaurantes": 0, "eventos": 0},
                    "lat_sum": 0.0,
                    "lng_sum": 0.0,
                    "coords_count": 0,
                    "ratings_sum": 0.0,
                    "ratings_count": 0,
                }
            return municipios_data[name]

        for p in all_places:
            entry = get_or_create_muni(p.municipio)
            entry["total_recursos"] += 1
            entry["desglose"]["lugares"] += 1
            if p.coordenadas and "lat" in p.coordenadas and "lng" in p.coordenadas:
                entry["lat_sum"] += p.coordenadas["lat"]
                entry["lng_sum"] += p.coordenadas["lng"]
                entry["coords_count"] += 1
            if p.rating_promedio is not None and p.rating_promedio > 0:
                entry["ratings_sum"] += p.rating_promedio
                entry["ratings_count"] += 1

        for r in all_restaurants:
            entry = get_or_create_muni(r.municipio)
            entry["total_recursos"] += 1
            entry["desglose"]["restaurantes"] += 1
            if r.coordenadas and "lat" in r.coordenadas and "lng" in r.coordenadas:
                entry["lat_sum"] += r.coordenadas["lat"]
                entry["lng_sum"] += r.coordenadas["lng"]
                entry["coords_count"] += 1
            if r.calificacion is not None and r.calificacion > 0:
                entry["ratings_sum"] += r.calificacion
                entry["ratings_count"] += 1

        for e in all_events:
            entry = get_or_create_muni(e.municipio)
            entry["total_recursos"] += 1
            entry["desglose"]["eventos"] += 1
            if e.coordenadas and "lat" in e.coordenadas and "lng" in e.coordenadas:
                entry["lat_sum"] += e.coordenadas["lat"]
                entry["lng_sum"] += e.coordenadas["lng"]
                entry["coords_count"] += 1

        if not municipios_data:
            return []

        max_count = max(item["total_recursos"] for item in municipios_data.values())
        max_count = max_count if max_count > 0 else 1

        result = []
        for muni_name, item in municipios_data.items():
            coords_count = item["coords_count"]
            centroide = {
                "lat": round(item["lat_sum"] / coords_count, 6) if coords_count > 0 else 20.671956,
                "lng": round(item["lng_sum"] / coords_count, 6) if coords_count > 0 else -103.344933,
            }
            rating_prom = (
                round(item["ratings_sum"] / item["ratings_count"], 2)
                if item["ratings_count"] > 0
                else 4.2
            )
            heat_score = round(item["total_recursos"] / max_count, 3)

            result.append({
                "municipio": muni_name,
                "total_recursos": item["total_recursos"],
                "coordenadas_centro": centroide,
                "desglose": item["desglose"],
                "rating_promedio": rating_prom,
                "heat_score": heat_score,
            })

        result.sort(key=lambda x: x["total_recursos"], reverse=True)
        return result


