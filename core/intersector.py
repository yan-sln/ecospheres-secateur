import processing  # type: ignore
from qgis.core import (
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsProcessingFeedback,
    QgsProcessingContext
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


def _reproject_layer(layer, target_crs, feedback=None, context=None):
    """
    Reprojette une couche (vecteur ou raster) vers target_crs.
    Retourne une couche en mémoire (memory) avec le CRS cible.
    """
    if layer.crs() == target_crs:
        return layer

    context = context or QgsProcessingContext()
    feedback = feedback or QgsProcessingFeedback()

    # --- VECTEUR ---
    if isinstance(layer, QgsVectorLayer):
        params = {
            'INPUT': layer,
            'TARGET_CRS': target_crs.toWkt(),
            'OUTPUT': 'memory:'
        }
        result = processing.run("native:reprojectlayer", params, context=context, feedback=feedback)
        reprojected_layer = result['OUTPUT']
        if isinstance(reprojected_layer, QgsVectorLayer):
            reprojected_layer.setName(layer.name() + "_reproj")
        if isinstance(reprojected_layer, str):
            reprojected_layer = QgsVectorLayer(reprojected_layer, layer.name() + "_reproj", "ogr")
        return reprojected_layer

    # --- RASTER ---
    if isinstance(layer, QgsRasterLayer):
        params = {
            'INPUT': layer.source(),
            'TARGET_CRS': target_crs.toWkt(),
            'RESAMPLING': 0,  # nearest neighbor
            'NODATA': None,
            'TARGET_RESOLUTION': None,
            'OPTIONS': '',
            'DATA_TYPE': 0,
            'TARGET_EXTENT': None,
            'TARGET_EXTENT_CRS': None,
            'MULTITHREADING': True,
            'EXTRA': '',
            'OUTPUT': 'TEMPORARY_OUTPUT'
        }
        result = processing.run("gdal:warpreproject", params, context=context, feedback=feedback)
        reprojected_layer = QgsRasterLayer(result['OUTPUT'], layer.name() + "_reproj")
        return reprojected_layer

    raise ValueError(f"Unsupported layer type: {type(layer)}")

# ---------------- INTERSECTION ---------------- #


def intersect_layer(source_layer, layers, progress_callback=None):
    results = []
    project = QgsProject.instance()
    if project is None:
        return results

    # CRS du projet
    project_crs = project.crs()

    # Add source layer as first result
    source_layer_proj = _reproject_layer(source_layer, project_crs)
    results.append(source_layer_proj)

    for i, layer in enumerate(layers):
        if progress_callback:
            progress_callback(i, len(layers), layer.name())

        if layer is None or layer == source_layer:
            continue

        # Reproject overlay to project CRS
        overlay_for_query = _reproject_layer(layer, project_crs)

        # Fix possible invalid geometries
        fixed = processing.run(
            "native:fixgeometries",
            {"INPUT": overlay_for_query, "OUTPUT": "memory:"},
        )
        clean_overlay = fixed["OUTPUT"]

        # Extract features that intersect source_layer_proj
        extract = processing.run(
            "native:extractbylocation",
            {
                "INPUT": clean_overlay,
                "PREDICATE": [0],  # intersects
                "INTERSECT": source_layer_proj,
                "OUTPUT": "memory:",
            },
        )
        mem_layer = extract["OUTPUT"]
        mem_layer.setName(f"{layer.name()} - intersect")
        try:
            mem_layer.setRenderer(layer.renderer().clone())
        except Exception:
            pass

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
