from qgis.core import (
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsVectorLayer,
)
import processing  # type: ignore


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
    
    # Add source layer as special intersected object for PDF export
    results.insert(0, source_layer)

    source_crs = source_layer.crs()

    for i, layer in enumerate(layers):
        if progress_callback:
            progress_callback(i, len(layers), layer.name())

        if layer is None or layer == source_layer:
            continue

        # Ensure both layers share the same CRS for spatial queries
        if source_crs != layer.crs():
            # Reproject overlay (shapefile) to source CRS (WFS)
            reproj = processing.run(
                "native:reprojectlayer",
                {
                    "INPUT": layer,
                    "TARGET_CRS": source_crs,
                    "OUTPUT": "memory:",
                },
            )
            overlay_for_query = reproj["OUTPUT"]
        else:
            overlay_for_query = layer

        # Fix possible invalid geometries in the overlay
        fixed = processing.run(
            "native:fixgeometries",
            {
                "INPUT": overlay_for_query,
                "OUTPUT": "memory:",
            },
        )
        clean_overlay = fixed["OUTPUT"]

        # Extract whole features that intersect the source (keep original geometry & attributes)
        extract = processing.run(
            "native:extractbylocation",
            {
                "INPUT": clean_overlay,
                "PREDICATE": [0],  # 0 = intersects
                "INTERSECT": source_layer,
                "OUTPUT": "memory:",
            },
        )
        mem_layer = extract["OUTPUT"]

        # Preserve original layer name and symbology
        mem_layer.setName(f"{layer.name()} — résultat")
        try:
            mem_layer.setRenderer(layer.renderer().clone())
        except Exception:
            pass

        # Keep only non‑empty results
        if mem_layer.featureCount() > 0:
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
