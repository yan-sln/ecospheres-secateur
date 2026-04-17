"""Entity selector utilities for communes, sections, and parcelles.

This module provides a thin compatibility layer around the ``geoselector``
library, exposing functions that the UI can call to list entities and fetch
geometries. It replaces the older ``commune_selector`` which only handled
communes.
"""

import json
import logging

from qgis.core import QgsGeometry, QgsJsonUtils

logger = logging.getLogger(__name__)

# Attempt to import geoselector; if unavailable, provide stub selectors.
try:
    from geoselector.core.entities import Commune, Parcelle, Section  # type: ignore
    from geoselector.core.selector import SelectorFactory  # type: ignore

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
    class StubSelector1:
        def select(self, *args, **kwargs):
            return []

        def get_geometry(self, *args, **kwargs):
            return None

        def clear_cache(self):
            pass

    _commune_selector = StubSelector1()
    _section_selector = StubSelector1()
    _parcelle_selector = StubSelector1()

# Ensure entity classes are defined for isinstance checks even when geoselector is unavailable
try:
    from geoselector.core.entities import Commune, Parcelle, Section  # type: ignore
except Exception:
    Commune = Parcelle = Section = object


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


def fetch_entity_geometry(entity) -> QgsGeometry | None:
    """Fetch the geometry of an entity and return it as a ``QgsGeometry``.
    Handles cases where the entity may lack a configured service.
    """
    # Ensure the entity has a service attached if missing
    if getattr(entity, "_service", None) is None:
        try:
            if isinstance(entity, Commune):
                entity.set_service(_commune_selector.service)
            elif isinstance(entity, Section):
                entity.set_service(_section_selector.service)
            elif isinstance(entity, Parcelle):
                entity.set_service(_parcelle_selector.service)
        except Exception:
            pass
    # Attempt to retrieve geometry via the entity method (force fetch)
    try:
        geojson = entity.get_geometry(force=True)
    except Exception:
        geojson = None

    # Fallback: use the appropriate selector's get_geometry if the direct call failed
    if not geojson:
        try:
            # Types are imported in the module scope when the geoselector is available
            if isinstance(entity, Commune):
                # Use the commune code as identifier for geometry fetch
                geojson = _commune_selector.get_geometry(entity.code)
            elif isinstance(entity, Section):
                # Section identifier is its "section" attribute
                geojson = _section_selector.get_geometry(entity.section)
            elif isinstance(entity, Parcelle):
                # Parcelle identifier is its "feature_id" attribute
                geojson = _parcelle_selector.get_geometry(entity.feature_id)
        except Exception:
            geojson = None

    if not geojson:
        return None

    # Validate that the returned geometry is a dict with a "type" key
    if not isinstance(geojson, dict) or "type" not in geojson:
        return None

    # Convert GeoJSON to QgsGeometry via QgsJsonUtils
    try:
        feature_collection = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "geometry": geojson, "properties": {}}],
            }
        )
        features = QgsJsonUtils.stringToFeatureList(feature_collection)
        return features[0].geometry() if features else None
    except Exception:
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
            from geoselector.core.entities import Commune, Parcelle, Section  # type: ignore
            from geoselector.core.selector import SelectorFactory  # type: ignore

            # Recreate selectors to clear their cache
            _commune_selector = SelectorFactory.create_selector(Commune)
            _section_selector = SelectorFactory.create_selector(Section)
            _parcelle_selector = SelectorFactory.create_selector(Parcelle)
        except Exception:
            # In case of complete failure, stay with stubs
            pass
