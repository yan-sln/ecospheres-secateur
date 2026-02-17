import csv
import os
import re

from PyQt5.QtCore import QDate, QDateTime, QTime
from PyQt5.QtXml import QDomDocument
from qgis.core import (
    QgsGeometry,
    QgsLayout,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsProject,
    QgsRasterLayer,
    QgsReadWriteContext,
    QgsReport,
    QgsReportSectionLayout,
    QgsVectorLayer,
)


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
        layer_name = layer.name().removesuffix(" — résultat")
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


def _load_template() -> QDomDocument:
    """Load the report_page.qpt template as a QDomDocument."""
    template_path = os.path.join(os.path.dirname(__file__), os.pardir, "resources", "report_page.qpt")
    doc = QDomDocument()
    with open(template_path, encoding="utf-8") as f:
        doc.setContent(f.read())
    return doc


def _make_page_layout(
    project: QgsProject,
    template_doc: QDomDocument,
    title: str,
    extent,
    visible_layers: list[QgsVectorLayer],
) -> QgsLayout:
    """Create a single-page QgsLayout from the template."""
    layout = QgsLayout(project)
    layout.initializeDefaults()
    ctx = QgsReadWriteContext()
    layout.loadFromTemplate(template_doc, ctx)

    # Set title
    title_item = layout.itemById("title")
    if title_item and isinstance(title_item, QgsLayoutItemLabel):
        title_item.setText(title)

    # Set map extent and layers
    map_item = layout.itemById("map")
    if map_item and isinstance(map_item, QgsLayoutItemMap):
        map_item.zoomToExtent(extent)
        map_item.setLayers(visible_layers)
        map_item.setKeepLayerSet(True)

    return layout


def _create_basemap() -> QgsRasterLayer:
    """Create an IGN Plan IGN v2 basemap layer with low opacity."""
    from urllib.parse import quote

    tile_url = (
        "https://data.geopf.fr/wmts"
        "?REQUEST=GetTile&SERVICE=WMTS&VERSION=1.0.0"
        "&TILEMATRIXSET=PM"
        "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"
        "&STYLE=normal&FORMAT=image/png"
        "&TILECOL={x}&TILEROW={y}&TILEMATRIX={z}"
    )
    # Encode & so it doesn't clash with QGIS URI parameter separators
    uri = f"type=xyz&url={quote(tile_url, safe=':/?={}.')}&zmax=19&zmin=0"
    layer = QgsRasterLayer(uri, "Plan IGN", "wms")
    layer.setOpacity(0.5)
    return layer


def export_results_to_pdf(
    result_layers: list[QgsVectorLayer],
    commune_name: str,
    commune_geom: QgsGeometry,
    output_path: str,
    progress_callback=None,
):
    """Export a multi-page PDF report: overview page + one page per result layer.

    progress_callback(current, total, name) is called before each page is built.
    """
    project = QgsProject.instance()
    template_doc = _load_template()
    basemap = _create_basemap()

    # Buffered extent (5% margin)
    bbox = commune_geom.boundingBox()
    bbox.grow(bbox.width() * 0.05 + bbox.height() * 0.05)

    total_pages = 1 + len(result_layers)
    report = QgsReport(project)

    # Page 1: overview with all result layers
    if progress_callback:
        progress_callback(0, total_pages, commune_name)
    overview_layout = _make_page_layout(project, template_doc, commune_name, bbox, list(result_layers) + [basemap])
    overview_section = QgsReportSectionLayout(report)
    overview_section.setBody(overview_layout)
    overview_section.setBodyEnabled(True)
    report.appendChild(overview_section)

    # Pages 2..N: one per result layer
    for i, layer in enumerate(result_layers):
        layer_name = layer.name().removesuffix(" — résultat")
        if progress_callback:
            progress_callback(i + 1, total_pages, layer_name)
        page_layout = _make_page_layout(project, template_doc, layer_name, bbox, [layer, basemap])
        section = QgsReportSectionLayout(report)
        section.setBody(page_layout)
        section.setBodyEnabled(True)
        report.appendChild(section)

    # Export
    if progress_callback:
        progress_callback(total_pages, total_pages, "Export PDF…")
    settings = QgsLayoutExporter.PdfExportSettings()
    # exportToPdf returns tuple[ExportResult, str] at runtime but qgis-stubs types it as ExportResult
    result, error = QgsLayoutExporter.exportToPdf(report, output_path, settings)  # pyright: ignore[reportGeneralTypeIssues]

    if result != QgsLayoutExporter.Success:
        raise RuntimeError(f"PDF export failed: {error}")
