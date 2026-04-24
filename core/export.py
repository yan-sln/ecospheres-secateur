import csv
import os
import re
from datetime import datetime

from qgis.core import (
    QgsMapLayer,
    QgsTextFormat,
    QgsLayerTreeGroup,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLegendStyle,
    QgsProject,
    QgsRectangle,
    QgsUnitTypes,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QTime  # noqa: UP035
from qgis.PyQt.QtGui import QFont  # noqa: UP035

# Import helpers from geopdf_utils
from .geopdf_utils import (
    _construire_legende,
    _exporter_legende_separee,
    ajouter_cadre_titre,
    ajouter_copyright,
    ajouter_credits_fdp,
    ajouter_echelle,
    ajouter_fleche_nord,
    ajouter_logo,
    ajouter_titre,
    creer_layout,
    nettoyer_layouts,
)
from .logger import logger


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


def export_results_to_csv(
    result_layers: list[QgsVectorLayer],
    output_dir: str,
    progress_callback=None,
) -> list[str]:
    """Export each result layer as a separate CSV file inside output_dir.

    Creates output_dir if it doesn't exist. Returns the list of written file paths.
    progress_callback(current, total, name) is called before each layer.
    """
    os.makedirs(output_dir, exist_ok=True)
    total = len(result_layers)

    written = []
    for i, layer in enumerate(result_layers):
        if not isinstance(layer, QgsVectorLayer):
            continue  # Skip non‑vector layers such as basemap
        layer_name = layer.name().removesuffix(" - intersect")
        if progress_callback:
            progress_callback(i, total, layer_name)

        filename = _safe_filename(layer_name) + ".csv"
        filepath = os.path.join(output_dir, filename)

        field_names = [field.name() for field in layer.fields()]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(field_names)
            for feat in layer.getFeatures():
                row = [_format_value(v) for v in feat.attributes()]
                writer.writerow(row)

        written.append(filepath)

    return written


# ============================================================
# EXPORT PRINCIPAL
# ============================================================


def export_results_to_pdf(
    result_layers: list[QgsVectorLayer],
    output_path: str,
    progress_callback=None,
    basemap_layer: QgsMapLayer | None = None,
):
    """Export a PDF (GeoPDF) report for the given result layers.

    Uses helper functions from ``core.geopdf_utils`` and logs actions via the
    plugin‑wide QGIS logger.
    """
    # Resolve output path – create a dated filename if a directory is supplied
    try:
        if os.path.isdir(output_path):
            date_hm = datetime.now().strftime("%Y_%m_%d_%Hh_%Mmin")
            filename = f"Rapport_cartographique_d_interrogation_ADS_des_parcelles_{date_hm}.pdf"
            full_path = os.path.join(output_path, filename)
        else:
            full_path = output_path
            date_hm = datetime.now().strftime("%Y_%m_%d_%Hh_%Mmin")
    except Exception as e:
        logger.error(f"Failed to resolve output path '{output_path}': {e}")
        raise

    if not result_layers:
        raise ValueError("result_layers must contain at least one layer for extent calculation")

    # Compute map extent from the first layer (add 5 % buffer)
    src_layer = result_layers[0]
    bbox = src_layer.extent() if isinstance(src_layer, QgsVectorLayer) else src_layer.boundingBox()
    bbox.grow(bbox.width() * 0.05 + bbox.height() * 0.05)
    rec_emprise = [bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum()]
    extent_rect = QgsRectangle(*rec_emprise)

    # -----------------------------------------------------------------
    # Hide all layers individually, then enable only result_layers
    # -----------------------------------------------------------------
    try:
        root = QgsProject.instance().layerTreeRoot()
        # Hide every layer in the project
        for layer_node in root.findLayers():
            layer_node.setItemVisibilityChecked(False)
    except Exception as exc:
        logger.exception("Failed to hide all layers before PDF export: %s", exc)
        raise

    visible_count = 0
    for layer in result_layers:
        try:
            tree_layer = root.findLayer(layer.id())
            if tree_layer:
                # Ensure parent groups are visible
                parent = tree_layer.parent()
                while parent and isinstance(parent, QgsLayerTreeGroup):
                    parent.setItemVisibilityChecked(True)
                    parent = parent.parent()
                tree_layer.setItemVisibilityChecked(True)
                visible_count += 1
        except Exception as exc:
            logger.exception("Could not set visibility for layer %s: %s", layer.name(), exc)
            # continue – a single failure should not abort the whole export

    if visible_count == 0:
        logger.warning("export_results_to_pdf called with result_layers but none could be made visible")

    # If a basemap layer is provided, make it visible as well
    if basemap_layer is not None:
        try:
            tree_layer = root.findLayer(basemap_layer.id())
            if tree_layer:
                parent = tree_layer.parent()
                while parent and isinstance(parent, QgsLayerTreeGroup):
                    parent.setItemVisibilityChecked(True)
                    parent = parent.parent()
                tree_layer.setItemVisibilityChecked(True)
                visible_count += 1
        except Exception as exc:
            logger.exception("Could not set visibility for basemap layer %s: %s", basemap_layer.name(), exc)

    # Layer names for the legend
    layer_names = [lyr.name() for lyr in result_layers]

    # Progress callback – signal start of heavy layout work
    if progress_callback:
        progress_callback(0, 1, "Export GeoPDF")

    # ---------------------------------------------------------------------
    # Build layout using geopdf_utils helpers
    # ---------------------------------------------------------------------
    project = QgsProject.instance()
    manager = project.layoutManager()
    nettoyer_layouts(manager)
    layout_name = f"GeoPDF_{date_hm}"
    layout = creer_layout(project, manager, layout_name)

    # Map item
    map_item = QgsLayoutItemMap(layout)
    map_item.setRect(20, 20, 20, 20)
    map_item.setExtent(extent_rect)
    map_item.attemptMove(QgsLayoutPoint(5, 26, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(240, 180, QgsUnitTypes.LayoutMillimeters))
    layout.addLayoutItem(map_item)

    # Title and surrounding frame
    ajouter_titre(layout, "Rapport")
    ajouter_cadre_titre(layout, largeur_page=295.0)

    # Scale bar, north arrow, logo, copyright and credits
    ajouter_echelle(layout, map_item, extent_rect)
    ajouter_fleche_nord(layout)
    ajouter_logo(layout)
    ajouter_copyright(layout)
    ajouter_credits_fdp(layout)

    # Legend handling – use iface when available, otherwise skip
    nb_items = 0
    try:
        legend, nb_items = _construire_legende(layout, map_item, layer_names)
    except Exception as e:
        logger.error(f"Failed to build legend: {e}")
        legend = None
        nb_items = 0

    # If too many items, export legend separately and remove from main layout
    seuil_legende_interne = 12
    if nb_items >= seuil_legende_interne and legend is not None:
        layout.removeLayoutItem(legend)
        try:
            _exporter_legende_separee(os.path.dirname(full_path), layer_names, nb_items, date_hm, extent_rect)
        except Exception as e:
            logger.warning(f"External legend export failed: {e}")

    # Export to GeoPDF
    exporter = QgsLayoutExporter(layout)
    exporter.layout().refresh()
    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = 300
    settings.writeGeoPdf = True
    try:
        exporter.exportToPdf(full_path, settings)
    except Exception as e:
        logger.error(f"GeoPDF export failed: {e}")
        raise RuntimeError(f"GeoPDF export failed: {e}")

    # Restore all layers visibility after export
    try:
        root.setItemVisibilityChecked(True)
    except Exception as exc:
        logger.exception("Failed to restore layer visibility after PDF export: %s", exc)
    # Clean up temporary layouts
    nettoyer_layouts(manager)

    logger.info(f"GeoPDF exported to: {full_path}")
    return full_path, nb_items
