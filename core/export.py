import csv
import os

from qgis.core import (
    QgsLayoutExporter,
    QgsLayoutItemMap,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsMapLayer,
    QgsProcessingFeedback,
    QgsProject,
    QgsRectangle,
    QgsUnitTypes,
    QgsVectorLayer,
)

# Import helpers from geopdf_utils
from .geopdf_utils import (
    _add_frame_title,
    _export_separate_legend,
    _make_legend,
    add_copyright,
    add_logo,
    add_map_credits,
    add_north_arrow,
    add_scale,
    add_title,
)
from .logger import logger
from .utils import (
    _format_value,
    _safe_filename,
    clean_layouts,
    create_layout,
    is_simple_fill,
    iterate_layers,
    set_layer_and_parents_visible,
    set_layer_opacity,
    temporary_visibility,
    timestamp_str,
)

# ============================================================
# EXPORT CSV
# ============================================================


def export_results_to_csv(
    result_layers: list[QgsVectorLayer],
    output_dir: str,
    feedback: QgsProcessingFeedback | None = None,
) -> list[str]:
    """Export each result layer as a separate CSV file inside output_dir.

    Creates output_dir if it doesn't exist. Returns the list of written file paths.
    progress.update(current, total, name) is called before each layer if a progress object is provided.
    """
    os.makedirs(output_dir, exist_ok=True)

    written = []

    def _write_csv(layer: QgsVectorLayer):
        """Callback used by :func:`iterate_layers` to write one CSV file.

        Skips non‑vector layers to preserve existing behaviour.
        """
        if not isinstance(layer, QgsVectorLayer):
            return
        filename = _safe_filename(layer.name()) + ".csv"
        filepath = os.path.join(output_dir, filename)

        field_names = [field.name() for field in layer.fields()]
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(field_names)
            for feat in layer.getFeatures():
                writer.writerow([_format_value(v) for v in feat.attributes()])

        written.append(filepath)
        logger.info(f"CSV exported to: {filepath}")

    iterate_layers(result_layers, _write_csv, feedback)

    return written


# ============================================================
# EXPORT GEOPDF
# ============================================================


def export_results_to_pdf(
    result_layers: list[QgsVectorLayer],
    output_path: str,
    logo_path: str,
    feedback: QgsProcessingFeedback | None = None,
    basemap_layer: QgsMapLayer | None = None,
    author: str | None = None,
    title: str | None = None,
):
    """Export a PDF (GeoPDF) report for the given result layers.

    Uses helper functions from ``core.geopdf_utils`` and logs actions via the
    plugin‑wide QGIS logger.
    """
    # Resolve output path – create a dated filename if a directory is supplied
    try:
        if os.path.isdir(output_path):
            date_hm = timestamp_str()
            filename = f"Rapport_cartographique_{date_hm}.pdf"
            full_path = os.path.join(output_path, filename)
        else:
            full_path = output_path
            date_hm = timestamp_str()
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
    root = QgsProject.instance().layerTreeRoot()
    # Hide all layers using temporary_visibility context manager; no restoration
    with temporary_visibility(root):
        visible_count = 0

        def _make_visible(layer):
            """Callback for :func:`iterate_layers` to set opacity and visibility.

            Updates the outer ``visible_count`` variable.
            """
            nonlocal visible_count
            try:
                if is_simple_fill(layer):
                    set_layer_opacity(layer, opacity=0.8)
                visible_count += int(set_layer_and_parents_visible(root, layer))
            except Exception as exc:
                logger.exception("Could not set visibility for layer %s: %s", layer.name(), exc)
                # continue – a single failure should not abort the whole export

        iterate_layers(result_layers, _make_visible, feedback)

        if visible_count == 0:
            logger.warning("export_results_to_pdf called with result_layers but none could be made visible")

        # If a basemap layer is provided, make it visible as well
        if basemap_layer is not None:
            try:
                visible_count += int(set_layer_and_parents_visible(root, basemap_layer))
            except Exception as exc:
                logger.exception("Could not set visibility for basemap layer %s: %s", basemap_layer.name(), exc)

        # Layer names for the legend
        layer_names = [lyr.name() for lyr in result_layers]

        # Feedback callback – signal start of heavy layout work
        if feedback:
            feedback.setProgress(0)

        # ---------------------------------------------------------------------
        # Build layout using geopdf_utils helpers
        # ---------------------------------------------------------------------
        project = QgsProject.instance()
        manager = project.layoutManager()
        clean_layouts(manager)
        layout_name = f"GeoPDF_{date_hm}"
        layout = create_layout(project, manager, layout_name)

        # Map item
        map_item = QgsLayoutItemMap(layout)
        map_item.setRect(20, 20, 20, 20)
        map_item.setExtent(extent_rect)
        map_item.attemptMove(QgsLayoutPoint(5, 26, QgsUnitTypes.LayoutMillimeters))
        map_item.attemptResize(QgsLayoutSize(240, 180, QgsUnitTypes.LayoutMillimeters))
        layout.addLayoutItem(map_item)

        # Title and surrounding frame
        add_title(layout, title)
        _add_frame_title(layout, largeur_page=295.0)

        # Scale bar, north arrow, logo, copyright and credits
        add_scale(layout, map_item, extent_rect)
        add_north_arrow(layout)
        add_logo(layout, logo_path)
        if author:
            add_copyright(layout, author=author)
        else:
            add_copyright(layout)
        if basemap_layer is not None:
            add_map_credits(layout, f"© {basemap_layer.name()}")

        nb_items = 0
        try:
            legend, nb_items = _make_legend(layout, map_item, layer_names)
        except Exception as e:
            logger.error(f"Failed to build legend: {e}")
            legend = None
            nb_items = 0

        # If too many items, export legend separately and remove from main layout
        seuil_legende_interne = 12
        if nb_items >= seuil_legende_interne and legend is not None:
            layout.removeLayoutItem(legend)
            try:
                _export_separate_legend(
                    os.path.dirname(full_path), layer_names, nb_items, date_hm, extent_rect, logo_path
                )
            except Exception as e:
                logger.warning(f"External legend export failed: {e}")

        # Export to GeoPDF
        exporter = QgsLayoutExporter(layout)
        exporter.layout().refresh()
        settings = QgsLayoutExporter.PdfExportSettings()
        settings.dpi = 300
        settings.writeGeoPdf = True
        settings.forceVectorOutput = True
        settings.exportLayersAsVectors = True
        settings.exportMetadata = True
        try:
            exporter.exportToPdf(full_path, settings)
        except Exception as e:
            logger.error(f"GeoPDF export failed: {e}")
            raise RuntimeError(f"GeoPDF export failed: {e}") from e

    # Clean up temporary layouts
    clean_layouts(manager)

    logger.info(f"GeoPDF exported to: {full_path}")
    return full_path, nb_items
