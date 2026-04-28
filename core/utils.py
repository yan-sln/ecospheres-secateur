import os
import re

from qgis.core import (
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsProject,
    QgsFillSymbol,
    QgsMapLayer,
    QgsLayerTreeGroup,
    QgsPrintLayout,
    QgsSingleSymbolRenderer,
    QgsCategorizedSymbolRenderer,
    QgsRenderContext,
    QgsVectorLayer
)
from qgis.PyQt.QtCore import QFile
from qgis.PyQt.QtCore import QDate, QDateTime, QTime  # noqa: UP035

# ---------------- LAYERS ---------------- #


def _get_group_by_path(path):
    """Return the QgsLayerTreeGroup matching the hierarchical *path*.
    *path* is a list of group names, e.g. ["Paris", "Sections"].
    Returns ``None`` if any component is missing.
    """
    project = QgsProject.instance()
    if not project:
        return None

    node = project.layerTreeRoot()
    for name in path:
        if not node:
            return None
        node = next(
            (child for child in node.children()
             if isinstance(child, QgsLayerTreeGroup) and child.name() == name),
            None,
        )
    return node


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

# ──────────────────────────────────────────────
#  Gestion de la transparence
# ──────────────────────────────────────────────

def set_layer_opacity(layer, opacity):
    renderer = layer.renderer()
    if renderer is None:
        return
    context = QgsRenderContext()
    # Pour SingleSymbolRenderer
    if isinstance(renderer, QgsSingleSymbolRenderer):
        symbol = renderer.symbol()
        symbol.setOpacity(opacity)
    # Pour CategorizedSymbolRenderer
    elif isinstance(renderer, QgsCategorizedSymbolRenderer):
        for symbol in renderer.symbols(context):
            symbol.setOpacity(opacity)

def set_layer_and_parents_visible(root: QgsLayerTreeGroup, layer: QgsMapLayer) -> bool:
    """Make a layer and all its parent groups visible.

    Returns ``True`` if the layer was found in the tree and its visibility was
    changed, ``False`` otherwise.
    """
    tree_layer = root.findLayer(layer.id())
    if not tree_layer:
        return False

    parent = tree_layer.parent()
    while parent and isinstance(parent, QgsLayerTreeGroup):
        parent.setItemVisibilityChecked(True)
        parent = parent.parent()

    tree_layer.setItemVisibilityChecked(True)
    return True


def _set_layer_visibility(nom_couche, nom_groupe, visible):
    """Allume ou éteint une couche dans un groupe donné.

    Le groupe n'est allumé que si visible=True.
    Si visible=False, seule la couche est éteinte (le groupe
    peut contenir d'autres couches encore visibles).
    """
    root = QgsProject.instance().layerTreeRoot()
    groupe = root.findGroup(nom_groupe)
    couche = None
    if groupe is not None:
        if visible:
            groupe.setItemVisibilityChecked(True)
        for child in groupe.children():
            if child.name() == nom_couche:
                layers = QgsProject.instance().mapLayersByName(nom_couche)
                if layers:
                    couche = layers[0]
                    tree_layer = root.findLayer(couche.id())
                    if tree_layer:
                        tree_layer.setItemVisibilityChecked(visible)
                break
    return groupe, couche

# ──────────────────────────────────────────────
#  Petit utilitaire de chemin vers les icônes
# ──────────────────────────────────────────────


def _icons_dir():
    """Renvoie le chemin absolu du dossier resources du plugin, situé à la racine du projet."""
    # Le fichier géopdf_utils.py se trouve dans le sous‑dossier ``core`` ; le dossier ``resources`` est à la racine du dépôt
    basepath = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))
    return os.path.join(basepath, "resources").replace("\\", "/")


def get_icon_path(icon_name):
    """Renvoie le chemin complet d'une icône si elle existe, sinon ''."""
    path = os.path.join(_icons_dir(), icon_name)
    return path if QFile.exists(path) else ""

# ──────────────────────────────────────────────
#  Gestion des layouts
# ──────────────────────────────────────────────


def nettoyer_layouts(manager):
    """Supprime tous les layouts existants pour éviter les erreurs C++."""
    for layout in manager.printLayouts():
        manager.removeLayout(layout)


def creer_layout(project, manager, nom):
    """Crée un nouveau QgsPrintLayout nommé, en supprimant tout doublon existant."""
    for layout in manager.printLayouts():
        if layout.name() == nom:
            manager.removeLayout(layout)
            break

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(nom)
    manager.addLayout(layout)
    return layout


def is_simple_fill(layer):
    renderer = layer.renderer()
    if renderer is None:
        return False
    if isinstance(renderer, QgsSingleSymbolRenderer):
        return isinstance(renderer.symbol(), QgsFillSymbol)
    if isinstance(renderer, QgsCategorizedSymbolRenderer):
        context = QgsRenderContext()
        return all(isinstance(s, QgsFillSymbol) for s in renderer.symbols(context))
    return False

def _format_value(val):
    if val is None:
        return ""
    if isinstance(val, QDateTime):
        return val.toString("yyyy-MM-dd HH:mm:ss") if val.isValid() else ""
    if isinstance(val, QDate):
        return val.toString("yyyy-MM-dd") if val.isValid() else ""
    if isinstance(val, QTime):
        return val.toString("HH:mm:ss") if val.isValid() else ""
    return val


def _safe_filename(name: str) -> str:
    """Turn a layer name into a safe filename (no path separators, etc.)."""
    return re.sub(r"[^\w\s\-()]", "_", name).strip()
