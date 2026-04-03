from qgis.core import (
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsVectorLayer,
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
