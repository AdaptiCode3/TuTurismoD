import math
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

class DBSCANClusterer:
    def __init__(self, eps_km: float = 3.0, min_samples: int = 3):
        self.eps_km = eps_km
        self.min_samples = min_samples

    def cluster_resources(self, resources: list[dict]) -> dict:
        """
        Agrupa los recursos turísticos basándose en su densidad geográfica real usando DBSCAN.
        Si scikit-learn no está disponible, cae de vuelta a la heurística de municipios.
        """
        if not resources:
            return {}

        try:
            import numpy as np
            from sklearn.cluster import DBSCAN
        except ImportError:
            logger.warning("scikit-learn o numpy no están instalados. Usando fallback de municipio para el mapa analítico.")
            return self._fallback_municipio_clustering(resources)

        # 1. Extraer coordenadas (convertir a radianes para la métrica haversine)
        coords_rad = []
        valid_resources = []
        
        for res in resources:
            lat, lng = res.get("lat"), res.get("lng")
            if lat is not None and lng is not None:
                coords_rad.append([math.radians(lat), math.radians(lng)])
                valid_resources.append(res)
                
        if not coords_rad:
            return {}

        coords_array = np.array(coords_rad)

        # Radio ecuatorial de la Tierra en km
        earth_radius_km = 6371.0
        epsilon_radians = self.eps_km / earth_radius_km

        # 2. Ejecutar DBSCAN
        db = DBSCAN(eps=epsilon_radians, min_samples=self.min_samples, metric='haversine', algorithm='ball_tree')
        labels = db.fit_predict(coords_array)

        # 3. Agrupar resultados por etiqueta de clúster
        clusters_data = defaultdict(lambda: {
            "total": 0,
            "lugares": 0,
            "restaurantes": 0,
            "eventos": 0,
            "ratings_sum": 0.0,
            "ratings_count": 0,
            "lats": [],
            "lngs": []
        })

        for label, res in zip(labels, valid_resources):
            cluster_id = int(label)
            
            c_data = clusters_data[cluster_id]
            c_data["total"] += 1
            
            t = res.get("type", "")
            if t == "place":
                c_data["lugares"] += 1
            elif t == "restaurant":
                c_data["restaurantes"] += 1
            elif t == "event":
                c_data["eventos"] += 1
                
            rating = res.get("rating")
            if rating and isinstance(rating, (int, float)) and rating > 0:
                c_data["ratings_sum"] += float(rating)
                c_data["ratings_count"] += 1
                
            c_data["lats"].append(res["lat"])
            c_data["lngs"].append(res["lng"])

        # 4. Construir respuesta
        result = {}
        for cluster_id, c_data in clusters_data.items():
            # Determinar el nombre del clúster
            if cluster_id == -1:
                cluster_name = "Zonas Aisladas (Ruido)"
            else:
                # Hacer que el índice sea 1-based para los clústeres reales
                cluster_name = f"Corredor Turístico {cluster_id + 1}"
                
            # Calcular centroide
            avg_lat = sum(c_data["lats"]) / len(c_data["lats"])
            avg_lng = sum(c_data["lngs"]) / len(c_data["lngs"])
            
            avg_rating = c_data["ratings_sum"] / c_data["ratings_count"] if c_data["ratings_count"] > 0 else 0.0
            
            # El heat_score podría ser una combinación del volumen de recursos y el rating
            heat_score = (c_data["total"] * 0.5) + (avg_rating * 10)
            
            result[cluster_name] = {
                "total_recursos": c_data["total"],
                "coordenadas_centro": [avg_lat, avg_lng],
                "desglose": {
                    "lugares": c_data["lugares"],
                    "restaurantes": c_data["restaurantes"],
                    "eventos": c_data["eventos"]
                },
                "rating_promedio": round(avg_rating, 1),
                "heat_score": round(heat_score, 1)
            }
            
        return result

    def _fallback_municipio_clustering(self, resources: list[dict]) -> dict:
        """Fallback que agrupa por municipio si sklearn no está."""
        municipio_data = defaultdict(lambda: {
            "total": 0,
            "lugares": 0,
            "restaurantes": 0,
            "eventos": 0,
            "ratings_sum": 0.0,
            "ratings_count": 0,
            "lats": [],
            "lngs": []
        })
        
        for res in resources:
            mun = res.get("municipio", "Desconocido")
            m_data = municipio_data[mun]
            m_data["total"] += 1
            
            t = res.get("type", "")
            if t == "place":
                m_data["lugares"] += 1
            elif t == "restaurant":
                m_data["restaurantes"] += 1
            elif t == "event":
                m_data["eventos"] += 1
                
            rating = res.get("rating")
            if rating and isinstance(rating, (int, float)) and rating > 0:
                m_data["ratings_sum"] += float(rating)
                m_data["ratings_count"] += 1
                
            lat, lng = res.get("lat"), res.get("lng")
            if lat is not None and lng is not None:
                m_data["lats"].append(lat)
                m_data["lngs"].append(lng)
                
        result = {}
        for mun, m_data in municipio_data.items():
            if not m_data["lats"]:
                continue
                
            avg_lat = sum(m_data["lats"]) / len(m_data["lats"])
            avg_lng = sum(m_data["lngs"]) / len(m_data["lngs"])
            avg_rating = m_data["ratings_sum"] / m_data["ratings_count"] if m_data["ratings_count"] > 0 else 0.0
            heat_score = (m_data["total"] * 0.5) + (avg_rating * 10)
            
            result[mun] = {
                "total_recursos": m_data["total"],
                "coordenadas_centro": [avg_lat, avg_lng],
                "desglose": {
                    "lugares": m_data["lugares"],
                    "restaurantes": m_data["restaurantes"],
                    "eventos": m_data["eventos"]
                },
                "rating_promedio": round(avg_rating, 1),
                "heat_score": round(heat_score, 1)
            }
            
        return result
