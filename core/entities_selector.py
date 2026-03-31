# -*- coding: utf-8 -*-
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
    from geoselector.core.selector import SelectorFactory
    from geoselector.core.entities import Commune, Section, Parcelle

    _commune_selector = SelectorFactory.create_selector(Commune)
    _section_selector = SelectorFactory.create_selector(Section)
    _parcelle_selector = SelectorFactory.create_selector(Parcelle)
except Exception:  # pragma: no cover
    # Fallback stubs that return empty results.
    class _StubSelector:
        def select(self, *args, **kwargs):
            return []

        def get_geometry(self, *args, **kwargs):
            return None

    _commune_selector = _StubSelector()
    _section_selector = _StubSelector()
    _parcelle_selector = _StubSelector()


def search_communes(text: str) -> list[dict]:
    """Search communes by name.

    Returns a list of ``{"nom": ..., "code": ...}`` dictionaries.
    """
    if len(text) < 2:
        return []
    raw_results = _commune_selector.select(text, limit=5)
    formatted = []
    for item in raw_results:
        formatted.append(
            {"nom": getattr(item, "name", ""), "code": getattr(item, "code", "")}
        )
    return formatted


def list_sections(commune_code: str) -> list[dict]:
    """List all cadastral sections for a given commune code.

    The underlying selector returns raw feature dictionaries; we forward them
    unchanged so the UI can decide how to display them.
    """
    # The selector expects the commune code as the first argument.
    return _section_selector.select(commune_code)


def list_parcelles(commune_code: str, section_code: str) -> list[dict]:
    """List all parcels for a given commune and section.

    ``section_code`` corresponds to the cadastral section identifier (e.g.
    "ZC"). The selector returns raw parcel dictionaries.
    """
    return _parcelle_selector.select(commune_code, section_code)


def fetch_parcel_geometry(parcel_id: str) -> QgsGeometry | None:
    """Fetch the geometry of a parcel and return it as a ``QgsGeometry``."""
    geojson = _parcelle_selector.get_geometry(parcel_id)
    if not geojson:
        return None
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
