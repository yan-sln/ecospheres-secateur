from qgis.core import (
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


# ---------------- LAYERS ---------------- #

def find_layers(exclude: QgsVectorLayer | None = None) -> list[QgsVectorLayer]:
    project = QgsProject.instance()
    if project is None:
        return []

    root = project.layerTreeRoot()
    if root is None:
        return []

    results = []
    _collect_layers(root, results, exclude)
    return results


def _collect_layers(group, out, exclude):
    for child in group.children():
        if isinstance(child, QgsLayerTreeGroup):
            if child.isVisible():
                _collect_layers(child, out, exclude)

        elif isinstance(child, QgsLayerTreeLayer):
            if not child.isVisible():
                continue

            layer = child.layer()

            if isinstance(layer, QgsVectorLayer) and layer != exclude:
                out.append(layer)


# ---------------- INTERSECTION ---------------- #

def intersect_layer(
    source_layer: QgsVectorLayer,
    layers: list[QgsVectorLayer],
    progress_callback=None,
) -> list[QgsVectorLayer]:

    results = []

    project = QgsProject.instance()
    if project is None:
        return results

    source_crs = source_layer.crs()

    source_features = list(source_layer.getSelectedFeatures())
    if not source_features:
        source_features = list(source_layer.getFeatures())

    for i, layer in enumerate(layers):
        if progress_callback:
            progress_callback(i, len(layers), layer.name())

        if layer is None or layer == source_layer:
            continue

        # ⚡ optimisation rapide
        if not layer.extent().intersects(source_layer.extent()):
            continue

        layer_crs = layer.crs()

        geom_type = QgsWkbTypes.displayString(layer.wkbType())

        mem_layer = QgsVectorLayer(
            f"{geom_type}?crs={layer_crs.authid()}",
            f"{layer.name()} — résultat",
            "memory",
        )

        provider = mem_layer.dataProvider()
        provider.addAttributes(layer.fields().toList())
        mem_layer.updateFields()

        transform = None
        if source_crs != layer_crs:
            try:
                transform = QgsCoordinateTransform(source_crs, layer_crs, project)
            except Exception:
                transform = None

        matches = []

        for src_feat in source_features:
            if not src_feat.hasGeometry():
                continue

            geom = QgsGeometry(src_feat.geometry())

            if transform:
                try:
                    geom.transform(transform)
                except Exception:
                    continue

            bbox = geom.boundingBox()
            
            # Met un buffer à 1 % ; désactivé sinon prend autre parcelle
            # bbox.grow(max(bbox.width(), bbox.height()) * 0.01)

            request = QgsFeatureRequest().setFilterRect(bbox)

            for feat in layer.getFeatures(request):
                if not feat.hasGeometry():
                    continue

                if geom.intersects(feat.geometry()):
                    new_feat = QgsFeature(mem_layer.fields())
                    new_feat.setGeometry(feat.geometry())
                    new_feat.setAttributes(feat.attributes())
                    matches.append(new_feat)

        if matches:
            provider.addFeatures(matches)
            mem_layer.updateExtents()
            results.append(mem_layer)

    if progress_callback:
        progress_callback(len(layers), len(layers), "")

    return results


# ---------------- PROJECT ---------------- #

def add_results_to_project(result_layers: list[QgsVectorLayer]):
    project = QgsProject.instance()
    if project is None:
        return

    root = project.layerTreeRoot()

    group = root.findGroup("Résultats secateur")
    if group:
        group.removeAllChildren()
    else:
        group = root.insertGroup(0, "Résultats secateur")

    for layer in result_layers:
        project.addMapLayer(layer, False)
        group.addLayer(layer)