from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)


def find_wfs_layers() -> list[QgsVectorLayer]:
    """Return visible WFS vector layers by walking the full layer tree."""
    project = QgsProject.instance()
    if project is None:
        return []
    root = project.layerTreeRoot()
    if root is None:
        return []
    results = []
    _collect_wfs_layers(root, results)
    return results


def _collect_wfs_layers(group: QgsLayerTreeGroup, out: list[QgsVectorLayer]):
    for child in group.children():
        if isinstance(child, QgsLayerTreeGroup):
            if child.isVisible():
                _collect_wfs_layers(child, out)
        elif isinstance(child, QgsLayerTreeLayer):
            if not child.isVisible():
                continue
            layer = child.layer()
            if isinstance(layer, QgsVectorLayer) and _is_wfs(layer):
                out.append(layer)


def _is_wfs(layer: QgsVectorLayer) -> bool:
    if layer.providerType().upper() == "WFS":
        return True
    # Some WFS layers are loaded via OGR — check source URI
    src = layer.source().lower()
    return "service=wfs" in src or "/wfs?" in src or "/wfs/" in src


def intersect_parcelle(
    parcelle_geom: QgsGeometry,
    layers: list[QgsVectorLayer],
    progress_callback=None,
) -> list[QgsVectorLayer]:
    """Intersect a parcel geometry with the given WFS layers.

    This function performs the actual intersection of parcel geometry with
    WFS layers, returning memory layers with matching features.
    """
    # Reproject parcel geometry to layer CRS
    parcelle_crs = QgsCoordinateReferenceSystem("EPSG:4326")
    results = []

    # Get project instance early to avoid repeated calls
    project = QgsProject.instance()
    if project is None:
        return results

    # Get layer tree root early
    root = project.layerTreeRoot()
    if root is None:
        return results

    for i, layer in enumerate(layers):
        if progress_callback:
            progress_callback(i, len(layers), layer.name())

        # Validate layer before proceeding
        if layer is None:
            continue

        # Reproject parcel geometry to layer CRS
        layer_crs = layer.crs()
        if layer_crs is None:
            continue

        local_geom = None

        # Try to transform geometry to layer CRS
        try:
            if layer_crs != parcelle_crs:
                transform = QgsCoordinateTransform(parcelle_crs, layer_crs, project)
                local_geom = QgsGeometry(parcelle_geom)
                if not local_geom.transform(transform):
                    # If transformation fails, fall back to original geometry
                    local_geom = parcelle_geom
            else:
                local_geom = parcelle_geom
        except Exception:
            # If any error occurs during transformation, use original geometry
            # Log the error for debugging but continue processing
            local_geom = parcelle_geom

        # Add a small buffer to the bounding box to ensure touching features are included
        bbox = local_geom.boundingBox()
        if not bbox.isEmpty():
            buffer_distance = max(bbox.width(), bbox.height()) * 0.01  # 1% buffer
            bbox.grow(buffer_distance)

        geom_type_str = QgsWkbTypes.displayString(layer.wkbType())
        mem_layer = QgsVectorLayer(
            f"{geom_type_str}?crs={layer.crs().authid()}",
            f"{layer.name()} — résultat",
            "memory",
        )
        mem_provider = mem_layer.dataProvider()

        # Validate memory layer provider
        if mem_provider is None:
            continue

        mem_provider.addAttributes(layer.fields().toList())
        mem_layer.updateFields()

        request = QgsFeatureRequest().setFilterRect(bbox)
        matching = []
        try:
            # Get features and iterate through them
            features = [feat for feat in layer.getFeatures(request)]
            for feat in features:
                # Validate feature before processing
                if feat is None or not feat.hasGeometry():
                    continue
                if local_geom.intersects(feat.geometry()):
                    new_feat = QgsFeature(mem_layer.fields())
                    new_feat.setGeometry(feat.geometry())
                    new_feat.setAttributes(feat.attributes())
                    matching.append(new_feat)
        except Exception:
            # If there's an error getting features, skip this layer
            continue

        if matching:
            mem_provider.addFeatures(matching)
            mem_layer.updateExtents()
            results.append(mem_layer)

    if progress_callback:
        progress_callback(len(layers), len(layers), "")

    return results


def add_results_to_project(result_layers: list[QgsVectorLayer]):
    """Add result layers to the project under a 'Résultats secateur' group."""
    project = QgsProject.instance()
    if project is None:
        return

    root = project.layerTreeRoot()
    if root is None:
        return

    group = root.findGroup("Résultats secateur")
    if group:
        group.removeAllChildren()
    else:
        group = root.insertGroup(0, "Résultats secateur")

    for layer in result_layers:
        project.addMapLayer(layer, False)
        if group is not None:
            group.addLayer(layer)
