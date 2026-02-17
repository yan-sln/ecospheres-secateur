import json
import urllib.parse
import urllib.request

from qgis.core import QgsGeometry, QgsJsonUtils

API_BASE = "https://geo.api.gouv.fr"


def search_communes(text: str) -> list[dict]:
    """Search communes by name. Returns [{"nom": "Dijon", "code": "21231"}, ...]."""
    if len(text) < 2:
        return []
    params = urllib.parse.urlencode(
        {
            "nom": text,
            "fields": "nom,code",
            "limit": "5",
        }
    )
    url = f"{API_BASE}/communes?{params}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        return [{"nom": c["nom"], "code": c["code"]} for c in data]
    except Exception:
        return []


def fetch_commune_geometry(code_insee: str) -> QgsGeometry | None:
    """Fetch the commune contour as QgsGeometry, or None on error."""
    params = urllib.parse.urlencode(
        {
            "geometry": "contour",
            "format": "geojson",
        }
    )
    url = f"{API_BASE}/communes/{code_insee}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        feature_collection = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": data["geometry"],
                        "properties": {},
                    }
                ],
            }
        )
        features = QgsJsonUtils.stringToFeatureList(feature_collection)
        if features:
            return features[0].geometry()
        return None
    except Exception:
        return None
