"""
core/repositories/geo_resolver.py
==================================
Servicio de resolución inteligente de municipios en Jalisco para los documentos
de la base de datos que no cuenten con dicho atributo guardado.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Centros de los municipios turísticos y principales de Jalisco
MUNICIPALITIES_CENTROIDS = {
    "Guadalajara": {"lat": 20.671956, "lng": -103.344933},
    "Zapopan": {"lat": 20.720894, "lng": -103.391697},
    "Tlaquepaque": {"lat": 20.638402, "lng": -103.313467},
    "Tonalá": {"lat": 20.624734, "lng": -103.243553},
    "Tlajomulco de Zúñiga": {"lat": 20.474635, "lng": -103.447432},
    "Tequila": {"lat": 20.885664, "lng": -103.837891},
    "Puerto Vallarta": {"lat": 20.653407, "lng": -105.228302},
    "Chapala": {"lat": 20.292500, "lng": -103.190278},
    "Mazamitla": {"lat": 19.916389, "lng": -103.019444},
    "Tapalpa": {"lat": 19.946389, "lng": -103.758889},
    "Lagos de Moreno": {"lat": 21.353333, "lng": -101.930833},
    "San Juan de los Lagos": {"lat": 21.244444, "lng": -102.333333},
}

# Mapeo de palabras clave encontradas en nombres/direcciones a su Municipio canónico
KEYWORD_MAPPINGS = {
    "guadalajara": "Guadalajara",
    " gdl": "Guadalajara",
    "zapopan": "Zapopan",
    "tlaquepaque": "Tlaquepaque",
    "tonala": "Tonalá",
    "tonalá": "Tonalá",
    "tlajomulco": "Tlajomulco de Zúñiga",
    "tequila": "Tequila",
    "vallarta": "Puerto Vallarta",
    "chapala": "Chapala",
    "ajijic": "Chapala",
    "mazamitla": "Mazamitla",
    "tapalpa": "Tapalpa",
    "lagos de moreno": "Lagos de Moreno",
    "san juan de los lagos": "San Juan de los Lagos",
}


def resolve_municipio(
    existing_value: Optional[str],
    coordenadas: Optional[dict[str, float]],
    direccion: str = "",
    nombre: str = "",
    descripcion: str = "",
) -> str:
    """
    Resuelve el municipio de forma inteligente basándose en la información disponible.
    """
    # 1. Si ya tiene un valor no vacío asignado y no es genérico, lo usamos
    val_clean = str(existing_value or "").strip().title()
    if val_clean and val_clean not in ("", "None", "Jalisco", "México", "Mexico", "Jal", "Jal."):
        # Normalizar nombres comunes
        if val_clean.lower() in ("san pedro tlaquepaque", "tlaquepaque"):
            return "Tlaquepaque"
        if "tonala" in val_clean.lower():
            return "Tonalá"
        if "guadalajara" in val_clean.lower():
            return "Guadalajara"
        if "zapopan" in val_clean.lower():
            return "Zapopan"
        if "tlajomulco" in val_clean.lower():
            return "Tlajomulco de Zúñiga"
        return val_clean

    # 2. Buscar palabras clave en la dirección, nombre o descripción
    text_to_search = f"{nombre} {direccion} {descripcion}".lower()
    for keyword, canonical_name in KEYWORD_MAPPINGS.items():
        if keyword in text_to_search:
            return canonical_name

    # 3. Si tiene coordenadas geográficas, encontrar el municipio más cercano por distancia
    if coordenadas and isinstance(coordenadas, dict):
        lat = coordenadas.get("lat")
        lng = coordenadas.get("lng")
        if lat and lng:
            min_dist = float("inf")
            closest_muni = "Guadalajara"
            for muni, coords in MUNICIPALITIES_CENTROIDS.items():
                dist = (lat - coords["lat"]) ** 2 + (lng - coords["lng"]) ** 2
                if dist < min_dist:
                    min_dist = dist
                    closest_muni = muni
            return closest_muni

    return "Guadalajara"
