import os
import re
from contextlib import contextmanager
from datetime import datetime

from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsFillSymbol,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsMapLayer,
    QgsPrintLayout,
    QgsProject,
    QgsRenderContext,
    QgsSingleSymbolRenderer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QFile, QTime  # noqa: UP035

from .constants import CREATED_OBJECTS_GROUP_NAME, RESULT_GROUP_NAME
from .logger import logger

# ──────────────────────────────────────────────
#  Layer utilities
# ──────────────────────────────────────────────


def get_or_create_group(path: list[str], clear: bool = False):
    """Return or create a QgsLayerTreeGroup.

    *path* – list of group names representing the hierarchy.
    If the group does not exist, it is created (including any missing parent
    groups). When *clear* is True, all children of the group are removed.
    """
    project = QgsProject.instance()
    if not project:
        return None

    node = project.layerTreeRoot()
    for name in path:
        if not node:
            return None
        node = next(
            (child for child in node.children() if isinstance(child, QgsLayerTreeGroup) and child.name() == name),
            None,
        )
        if node is None:
            break
    group = node

    if group is None:
        root = project.layerTreeRoot()
        if len(path) > 1:
            parent_path = path[:-1]
            parent_group = get_or_create_group(parent_path, clear=False)
            if parent_group is None:
                parent_group = root
            group = parent_group.insertGroup(0, path[-1])
        else:
            group = root.insertGroup(0, path[0])

    if clear and group is not None:
        group.removeAllChildren()

    return group


# ---------------------------------------------------------------------------
# Group helpers
# ---------------------------------------------------------------------------


def get_results_group(clear: bool = False):
    """Return the "Résultats secateur" group, creating it if necessary.
    Pass ``clear=True`` to empty the group before returning.
    """
    # Ensure group exists via get_or_create_group helper
    return get_or_create_group([RESULT_GROUP_NAME], clear=clear)


def get_created_objects_group(clear: bool = False):
    """Return the "Objets créés" group, creating it if necessary.
    Pass ``clear=True`` to empty the group before returning.
    """
    # Ensure group exists via get_or_create_group helper
    return get_or_create_group([CREATED_OBJECTS_GROUP_NAME], clear=clear)


def filter_out_source(layers: list[QgsVectorLayer], source: QgsVectorLayer) -> list[QgsVectorLayer]:
    """Return a new list of *layers* without the *source* layer.

    This helper centralises the exclusion logic used by several parts of the
    plugin, ensuring DRY code.
    """
    return [lyr for lyr in layers if lyr != source]


def find_layers(exclude: QgsVectorLayer | None = None) -> list[QgsVectorLayer]:
    """Return a list of visible vector layers in the current QGIS project.

    Args:
        exclude: Optional ``QgsVectorLayer`` that will be omitted from the result.

    Returns:
        List of ``QgsVectorLayer`` instances that are visible and not excluded.
    """
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
    """Recursively collect visible vector layers from a layer tree group.

    Args:
        group: ``QgsLayerTreeGroup`` to traverse.
        out: List to which found ``QgsVectorLayer`` objects are appended.
        exclude: Optional layer to exclude from collection.
    """
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
#  Transparency management
# ──────────────────────────────────────────────


def set_layer_opacity(layer, opacity):
    """Set the opacity of a layer's renderer symbols.

    Supports ``QgsSingleSymbolRenderer`` and ``QgsCategorizedSymbolRenderer``.
    If the layer has no renderer, the function does nothing.

    Args:
        layer: ``QgsMapLayer`` whose symbols' opacity will be modified.
        opacity: Float between 0 (transparent) and 1 (opaque).
    """
    renderer = layer.renderer()
    if renderer is None:
        return
    context = QgsRenderContext()

    if isinstance(renderer, QgsSingleSymbolRenderer):
        symbol = renderer.symbol()
        symbol.setOpacity(opacity)

    elif isinstance(renderer, QgsCategorizedSymbolRenderer):
        for symbol in renderer.symbols(context):
            symbol.setOpacity(opacity)


# ──────────────────────────────────────────────
#  Visibility helpers
# ──────────────────────────────────────────────
@contextmanager
def temporary_visibility(root):
    """Hide all layers for the duration of the context.

    All layers are set to invisible when entering the context. Visibility
    changes made inside the block (e.g., making result layers visible) are
    retained after exiting; no restoration is performed.
    """
    # Hide every layer
    for node in root.findLayers():
        node.setItemVisibilityChecked(False)
    try:
        yield
    finally:
        # Intentionally do not restore original visibility to keep the
        # visibility state set within the context (result layers remain visible).
        pass


def set_layer_and_parents_visible(root: QgsLayerTreeGroup, layer: QgsMapLayer) -> bool:
    """Make a layer and all its parent groups visible using QGIS recursive API.

    Returns ``True`` if the layer was found in the tree and its visibility was
    changed, ``False`` otherwise.
    """
    tree_layer = root.findLayer(layer.id())
    if not tree_layer:
        return False
    tree_layer.setItemVisibilityCheckedParentRecursive(True)
    tree_layer.setItemVisibilityChecked(True)
    return True


# ──────────────────────────────────────────────
#  Iteration helper
# ──────────────────────────────────────────────


def iterate_layers(layers, callback, feedback=None):
    """Iterate over *layers* and apply *callback* to each.

    ``feedback`` – optional :class:`QgsProcessingFeedback` instance.  If provided,
    its ``setProgress`` method is called with ``int(i / total * 100)`` before
    invoking the callback.  If the user cancels the associated task, the loop
    aborts early.
    """
    total = len(layers)
    for i, layer in enumerate(layers):
        if feedback:
            feedback.setProgress(int(i / total * 100))
            if getattr(feedback, "isCanceled", lambda: False)():
                logger.info("Export cancelled by user after %d/%d layers", i, total)
                break
        callback(layer)


# ──────────────────────────────────────────────
#  Icon utilities
# ──────────────────────────────────────────────


def _icons_dir():
    """Return the absolute path to the plugin's resources directory located at the project root."""
    # The file ``geopdf_utils.py`` resides in the ``core`` subdirectory;
    # the ``resources`` folder is at the repository root
    basepath = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), os.pardir))
    return os.path.join(basepath, "resources").replace("\\", "/")


def get_icon_path(icon_name):
    """Return the full path to an icon if it exists, otherwise an empty string."""
    path = os.path.join(_icons_dir(), icon_name)
    return path if QFile.exists(path) else ""


# ──────────────────────────────────────────────
#  Layout management
# ──────────────────────────────────────────────


def clean_layouts(manager):
    """Remove all existing layouts to avoid C++ errors."""
    for layout in manager.printLayouts():
        manager.removeLayout(layout)


def create_layout(project, manager, nom):
    """Create a new named ``QgsPrintLayout`` after removing any existing layout with the same name.

    Uses ``manager.layoutByName`` for direct lookup instead of iterating over all layouts.
    """
    # Directly obtain an existing layout with the given name, if any
    existing = manager.layoutByName(nom)
    if existing:
        manager.removeLayout(existing)

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(nom)
    manager.addLayout(layout)
    return layout


# ──────────────────────────────────────────────
#  Renderer checks
# ──────────────────────────────────────────────


def is_simple_fill(layer):
    """Determine if a layer's renderer uses only simple fill symbols.

    Returns ``True`` when the layer's renderer is a ``QgsSingleSymbolRenderer``
    with a ``QgsFillSymbol`` or a ``QgsCategorizedSymbolRenderer`` whose all
    category symbols are ``QgsFillSymbol`` instances. Otherwise returns ``False``.
    """
    renderer = layer.renderer()
    if renderer is None:
        return False
    if isinstance(renderer, QgsSingleSymbolRenderer):
        return isinstance(renderer.symbol(), QgsFillSymbol)
    if isinstance(renderer, QgsCategorizedSymbolRenderer):
        context = QgsRenderContext()
        return all(isinstance(s, QgsFillSymbol) for s in renderer.symbols(context))
    return False


# ──────────────────────────────────────────────
#  Value formatting & Filename safety
# ──────────────────────────────────────────────


def timestamp_str() -> str:
    """Return current datetime formatted as "YYYY_MM_DD_HHh_MMin".
    Centralises the timestamp format used for exported files.
    """
    return datetime.now().strftime("%Y_%m_%d_%Hh_%Mmin")


def _format_value(val):
    """Format various QGIS attribute values into string representations.

    Handles ``None`` (returns empty string) and QDate/QDateTime/QTime objects,
    converting them to ISO‑like strings. Other types are returned unchanged.
    """
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
