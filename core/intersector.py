from qgis.core import (
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
    root = QgsProject.instance().layerTreeRoot()
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


def intersect_commune(
    commune_geom: QgsGeometry,
    layers: list[QgsVectorLayer],
    progress_callback=None,
) -> list[QgsVectorLayer]:
    """Intersect commune geometry against each layer. Returns memory layers with matching features."""
    results = []
    for i, layer in enumerate(layers):
        if progress_callback:
            progress_callback(i, len(layers), layer.name())

        geom_type_str = QgsWkbTypes.displayString(layer.wkbType())
        mem_layer = QgsVectorLayer(
            f"{geom_type_str}?crs={layer.crs().authid()}",
            f"{layer.name()} — résultat",
            "memory",
        )
        mem_provider = mem_layer.dataProvider()
        mem_provider.addAttributes(layer.fields().toList())
        mem_layer.updateFields()

        request = QgsFeatureRequest().setFilterRect(commune_geom.boundingBox())
        matching = []
        for feat in layer.getFeatures(request):
            if feat.hasGeometry() and commune_geom.intersects(feat.geometry()):
                new_feat = QgsFeature(mem_layer.fields())
                new_feat.setGeometry(feat.geometry())
                new_feat.setAttributes(feat.attributes())
                matching.append(new_feat)

        if matching:
            mem_provider.addFeatures(matching)
            mem_layer.updateExtents()
            results.append(mem_layer)

    if progress_callback:
        progress_callback(len(layers), len(layers), "")

    return results


def add_results_to_project(result_layers: list[QgsVectorLayer]):
    """Add result layers to the project under a 'Résultats secateur' group."""
    root = QgsProject.instance().layerTreeRoot()

    group = root.findGroup("Résultats secateur")
    if group:
        group.removeAllChildren()
    else:
        group = root.insertGroup(0, "Résultats secateur")

    for layer in result_layers:
        QgsProject.instance().addMapLayer(layer, False)
        group.addLayer(layer)
