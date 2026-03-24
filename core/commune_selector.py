# -*- coding: utf-8 -*-
"""Adapter module that replaces the original ``commune_api`` with the generic
:mod:`geoselector` selector.

This module provides a thin compatibility layer so that existing code can keep
importing ``search_communes`` and ``fetch_commune_geometry`` unchanged while the
underlying implementation now relies on the high‑level ``geoselector`` selector.

The adapter:

* Instantiates a ``SelectorFactory`` selector for the :class:`geoselector.core.entities.Commune`
  entity (cached by the factory).
* ``search_communes`` forwards the text query to ``selector.select`` and normalises
  the result to a list of ``{"nom": ..., "code": ...}`` dictionaries, matching the
  original contract.
* ``fetch_commune_geometry`` forwards the INSEE code to ``selector.get_geometry``
  and converts the returned GeoJSON geometry dictionary into a ``QgsGeometry``
  using the same ``FeatureCollection`` conversion logic that the legacy module
  used.

The public API mirrors the previous implementation so that the rest of the
plugin can continue to import ``search_communes`` and ``fetch_commune_geometry``
without any changes.
"""

import json
from qgis.core import QgsGeometry, QgsJsonUtils

# geoselector imports
from geoselector.core.selector import SelectorFactory
from geoselector.core.entities import Commune

# Create a selector instance for the Commune entity. The selector is cached by
# ``SelectorFactory`` so this is cheap and safe to do at import time.
_selector = SelectorFactory.create_selector(Commune)


def search_communes(text: str) -> list[dict]:
    """Search communes by name using the geoselector selector.

    Parameters
    ----------
    text: str
        The name fragment to search for.

    Returns
    -------
    list[dict]
        A list of dictionaries with the keys ``"nom"`` and ``"code"`` matching
        the original ``commune_api`` contract.
    """
    if len(text) < 2:
        return []
    # The selector returns a list of ``GeoEntity`` instances (or raw feature
    # dictionaries depending on the handler configuration). We normalise the
    # result to the expected ``{"nom": ..., "code": ...}`` shape.
    raw_results = _selector.select(text)
    formatted = []
    for item in raw_results:
        formatted.append({"nom": item.name, "code": item.code})  # type: ignore[attr-defined]
    return formatted


def fetch_commune_geometry(code_insee: str) -> QgsGeometry | None:
    """Fetch the geometry of a commune and return it as a ``QgsGeometry``.

    The selector returns a GeoJSON geometry dictionary. We wrap it in a minimal
    FeatureCollection and reuse the same conversion logic that the original
    ``commune_api`` used.
    """
    # ``_selector.get_geometry`` returns a raw GeoJSON geometry dict or ``None``.
    geojson = _selector.get_geometry(code_insee)
    if not geojson:
        return None
    # Build a FeatureCollection JSON string compatible with ``QgsJsonUtils``.
    feature_collection = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": geojson,
                    "properties": {},
                }
            ],
        }
    )
    features = QgsJsonUtils.stringToFeatureList(feature_collection)
    if features:
        return features[0].geometry()
    return None
