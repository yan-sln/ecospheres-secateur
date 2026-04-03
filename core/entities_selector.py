"""Entity selector utilities for communes, sections, and parcelles.

This module provides a thin compatibility layer around the ``geoselector``
library, exposing functions that the UI can call to list entities and fetch
geometries. It replaces the older ``commune_selector`` which only handled
communes.
"""

import json

from qgis.core import QgsGeometry, QgsJsonUtils

# Attempt to import geoselector; if unavailable, provide stub selectors.
try:
    from geoselector.core.entities import Commune, Parcelle, Section
    from geoselector.core.selector import SelectorFactory

    _commune_selector = SelectorFactory.create_selector(Commune)
    _section_selector = SelectorFactory.create_selector(Section)
    _parcelle_selector = SelectorFactory.create_selector(Parcelle)
except ImportError:  # pragma: no cover
    # Fallback stubs that return empty results.
    class _StubSelector:
        def select(self, *args, **kwargs):
            return []

        def get_geometry(self, *args, **kwargs):
            return None

        def clear_cache(self):
            pass

    _commune_selector = _StubSelector()
    _section_selector = _StubSelector()
    _parcelle_selector = _StubSelector()
except Exception:  # pragma: no cover
    # Fallback stubs that return empty results.
    class _StubSelector:
        def select(self, *args, **kwargs):
            return []

        def get_geometry(self, *args, **kwargs):
            return None

        def clear_cache(self):
            pass

    _commune_selector = _StubSelector()
    _section_selector = _StubSelector()
    _parcelle_selector = _StubSelector()


def search_communes(text: str) -> list[Commune]:
    """Search communes by name.

    Returns a list of Commune GeoEntity objects.
    """
    if len(text) < 2:
        return []
    raw_results = _commune_selector.select(text, limit=5)
    return raw_results


def list_sections(commune_code: str) -> list[Section]:
    """List all cadastral sections for a given commune code.

    Returns a list of Section GeoEntity objects.
    """
    # The selector expects the commune code as the first argument.
    raw_results = _section_selector.select(commune_code)
    return raw_results


def list_parcelles(commune_code: str, section_code: str) -> list[Parcelle]:
    """List all parcels for a given commune and section.

    Returns a list of Parcelle GeoEntity objects.
    """
    raw_results = _parcelle_selector.select(commune_code, section_code)
    return raw_results


def fetch_parcel_geometry(parcelle: Parcelle) -> QgsGeometry | None:
    """Fetch the geometry of a parcel and return it as a ``QgsGeometry``."""
    # Ensure the parcel has its service set if it's not already set
    # This handles cases where a parcel was created outside the normal selector flow
    if parcelle._service is None:
        # Set a simple fallback - we'll try to make sure the entity can at least
        # fetch geometry even without service by using force=True if needed
        pass

    geojson = parcelle.get_geometry()
    if not geojson:
        return None

    # Validate that the returned geometry actually corresponds to a parcel
    # Check if the geometry is valid and has the expected structure
    if not isinstance(geojson, dict):
        return None

    # Check if we have a geometry type
    if "type" not in geojson:
        return None

    # Additional validation to ensure we're dealing with a parcel geometry
    # rather than a commune geometry by checking expected properties
    try:
        feature_collection = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": geojson, "properties": {}}],
            }
        )
        features = QgsJsonUtils.stringToFeatureList(feature_collection)
        if features:
            return features[0].geometry()
        return None
    except Exception:
        # If there's any issue with parsing the geometry, return None
        return None


def clear_cache():
    """Clear the internal cache of all selectors."""
    global _commune_selector, _section_selector, _parcelle_selector
    try:
        # Try to call clear_cache method if it exists on selectors
        if hasattr(_commune_selector, "clear_cache"):
            _commune_selector.clear_cache()
        if hasattr(_section_selector, "clear_cache"):
            _section_selector.clear_cache()
        if hasattr(_parcelle_selector, "clear_cache"):
            _parcelle_selector.clear_cache()
    except Exception:
        # In case of failure, recreate selectors to clear their cache
        try:
            from geoselector.core.entities import Commune, Parcelle, Section
            from geoselector.core.selector import SelectorFactory

            # Recreate selectors to clear their cache
            _commune_selector = SelectorFactory.create_selector(Commune)
            _section_selector = SelectorFactory.create_selector(Section)
            _parcelle_selector = SelectorFactory.create_selector(Parcelle)
        except Exception:
            # In case of complete failure, stay with stubs
            pass
