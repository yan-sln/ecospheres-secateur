import os
from datetime import datetime

from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QFont, QPolygonF
from qgis.core import (
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutItemPicture,
    QgsLayoutItemPolyline,
    QgsLayoutItemScaleBar,
    QgsLayoutMeasurement,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLegendStyle,
    QgsLineSymbol,
    QgsProject,
    QgsRectangle,
    QgsTextFormat,
    QgsUnitTypes,
)

from .utils import create_layout, get_icon_path

# ──────────────────────────────────────────────
#  Internal function
# ──────────────────────────────────────────────


def _make_rectangle_polygon(x1, y1, x2, y2):
    """Create a closed rectangular QPolygonF from corner coordinates.

    Parameters:
        x1, y1 (float): Lower‑left corner coordinates.
        x2, y2 (float): Upper‑right corner coordinates.

    Returns:
        QPolygonF: The rectangle polygon.
    """
    polygon = QPolygonF()
    polygon.append(QPointF(x1, y1))
    polygon.append(QPointF(x2, y1))
    polygon.append(QPointF(x2, y2))
    polygon.append(QPointF(x1, y2))
    polygon.append(QPointF(x1, y1))
    return polygon


def _frame_style():
    """Create and return a QgsLineSymbol configured for title frame borders.

    Returns:
        QgsLineSymbol: Symbol with predefined style suitable for title frames.
    """
    props = {
        "color": "0,5,0,55",
        "width": "2.0",
        "capstyle": "square",
        "style": "solid",
        "style_border": "solid",
        "color_border": "black",
        "width_border": "1.0",
        "joinstyle": "miter",
    }
    return QgsLineSymbol.createSimple(props)


# ──────────────────────────────────────────────
#  Basic layout elements
# ──────────────────────────────────────────────


def _add_frame_title(layout, largeur_page=295.0):
    """Add a rectangular frame around the title area at the top of the page.

    Parameters:
        layout (QgsLayout): The layout to which the frame will be added.
        largeur_page (float, optional): Page width in millimeters. Defaults to 295.0.

    Returns:
        QgsLayoutItemPolyline: The polyline item representing the frame.
    """
    polygon = _make_rectangle_polygon(2.0, 2.0, largeur_page, 25.0)
    polyline = QgsLayoutItemPolyline(polygon, layout)
    polyline.setSymbol(_frame_style())
    layout.addLayoutItem(polyline)
    return polyline


def ajouter_label(layout, texte, x, y, font_name="Arial", font_size=10):
    """Create a generic QgsLayoutItemLabel.

    Parameters
    ----------
    layout: QgsLayout
        Layout to which the label is added.
    texte: str
        Text to display.
    x, y: float
        Position in millimeters.
    font_name: str, optional
        Font family, default "Arial".
    font_size: int, optional
        Font size in points, default 10.
    """
    label = QgsLayoutItemLabel(layout)
    label.setText(texte)
    text_format = QgsTextFormat()
    text_format.setFont(QFont(font_name, font_size))
    label.setTextFormat(text_format)
    label.adjustSizeToText()
    layout.addLayoutItem(label)
    label.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return label


def add_title(layout, texte, x=7.0, y=5.0, font_name="Arial", font_size=13):
    """Add a title label to the layout and adjust its size to fit the given text.

    Parameters:
        layout (QgsLayout): The layout to modify.
        texte (str): Title text.
        x (float, optional): X position in millimeters. Defaults to 7.0.
        y (float, optional): Y position in millimeters. Defaults to 5.0.
        font_name (str, optional): Font family name. Defaults to "Arial".
        font_size (int, optional): Font size in points. Defaults to 13.

    Returns:
        QgsLayoutItemLabel: The created label item.
    """
    label = ajouter_label(layout, texte, x, y, font_name, font_size)
    w = x + label.boundingRect().width()
    h = y + label.boundingRect().height()
    label.attemptResize(QgsLayoutSize(w, h, QgsUnitTypes.LayoutMillimeters))
    return label


def add_scale(layout, map_item, canvas_extent, x=5.0, y=195.0):
    """Add a scale bar to the layout, automatically sized based on the canvas extent.

    Parameters:
        layout (QgsLayout): The layout to modify.
        map_item (QgsLayoutItemMap): The map item to link the scale bar to.
        canvas_extent (QgsRectangle): Extent used to determine appropriate scale.
        x (float, optional): X position in millimeters. Defaults to 5.0.
        y (float, optional): Y position in millimeters. Defaults to 195.0.

    Returns:
        QgsLayoutItemScaleBar: The created scale bar item.
    """
    scale_bar = QgsLayoutItemScaleBar(layout)
    scale_bar.applyDefaultSettings()
    scale_bar.setLinkedMap(map_item)
    scale_bar.setStyle("Single Box")
    scale_bar.setNumberOfSegmentsLeft(0)
    scale_bar.setNumberOfSegments(2)

    d_max = max(canvas_extent.height(), canvas_extent.width())
    bar_size = int(d_max / 5)
    scale_bar.setMapUnitsPerScaleBarUnit(1)

    # Table de seuils : (seuil_max, unité, label, taille_segment)
    _thresholds = [
        (20, QgsUnitTypes.DistanceMeters, "m", 5),
        (50, QgsUnitTypes.DistanceMeters, "m", 10),
        (100, QgsUnitTypes.DistanceMeters, "m", 20),
        (200, QgsUnitTypes.DistanceMeters, "m", 50),
        (300, QgsUnitTypes.DistanceMeters, "m", 75),
        (500, QgsUnitTypes.DistanceMeters, "m", 100),
        (1000, QgsUnitTypes.DistanceMeters, "m", 250),
        (2000, QgsUnitTypes.DistanceKilometers, "km", 0.2),
        (5000, QgsUnitTypes.DistanceKilometers, "km", 0.5),
        (10000, QgsUnitTypes.DistanceKilometers, "km", 1),
        (20000, QgsUnitTypes.DistanceKilometers, "km", 2),
        (50000, QgsUnitTypes.DistanceKilometers, "km", 5),
    ]
    for seuil, unite, label, segment in _thresholds:
        if bar_size <= seuil:
            scale_bar.setUnits(unite)
            scale_bar.setUnitLabel(label)
            scale_bar.setUnitsPerSegment(segment)
            break

    scale_bar.setBackgroundEnabled(True)
    layout.addLayoutItem(scale_bar)
    scale_bar.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return scale_bar


def add_north_arrow(layout, x=275.0, y=4.0):
    """Add a north arrow picture to the layout.

    Parameters:
        layout (QgsLayout): The layout to modify.
        x (float, optional): X position in millimeters. Defaults to 275.0.
        y (float, optional): Y position in millimeters. Defaults to 4.0.

    Returns:
        QgsLayoutItemPicture: The picture item representing the north arrow.
    """
    nord = QgsLayoutItemPicture(layout)
    path = get_icon_path("Nord.jpg")
    if path:
        nord.setPicturePath(path)
    layout.addLayoutItem(nord)
    nord.attemptResize(QgsLayoutSize(20, 20, QgsUnitTypes.LayoutMillimeters))
    nord.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return nord


def add_logo(layout, path, x=255.0, y=165.0, taille=30.0):
    """Add the prefecture/DDT logo picture to the layout.

    Parameters:
        layout (QgsLayout): The layout to modify.
        path
        x (float, optional): X position in millimeters. Defaults to 255.0.
        y (float, optional): Y position in millimeters. Defaults to 165.0.
        taille (float, optional): Size of the logo in millimeters (both width and height). Defaults to 30.0.
        icon_name (str, optional): Filename of the logo icon. Defaults to "PREF_Cote_d_Or_CMJN_295_432px_Marianne.jpg".

    Returns:
        QgsLayoutItemPicture: The picture item representing the logo.
    """
    logo = QgsLayoutItemPicture(layout)
    logo.setPicturePath(path)
    layout.addLayoutItem(logo)
    logo.attemptResize(QgsLayoutSize(taille, taille, QgsUnitTypes.LayoutMillimeters))
    logo.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return logo


def add_copyright(layout, x=250.0, y=200.0, author="DDT21", font_size=10):
    """Add a copyright label with the current date.

    Parameters:
        layout (QgsLayout): The layout to modify.
        x (float, optional): X position in millimeters. Defaults to 250.0.
        y (float, optional): Y position in millimeters. Defaults to 200.0.
        organisme (str, optional): Organization name. Defaults to "DDT21".
        font_size (int, optional): Font size in points. Defaults to 10.

    Returns:
        QgsLayoutItemLabel: The created label item.
    """
    date_str = datetime.strftime(datetime.now(), "%d/%m/%Y")
    texte = f"{author} le {date_str}"
    label = ajouter_label(layout, texte, x, y, font_name="Arial", font_size=font_size)
    label.attemptResize(QgsLayoutSize(40, 20, QgsUnitTypes.LayoutMillimeters))
    return label


def add_map_credits(layout, text: str, x=250.0, y=150.0):
    """Add the credits for IGN map sources.

    Parameters:
        layout (QgsLayout): The layout to modify.
        text (str): The text to display
        x (float, optional): X position in millimeters. Defaults to 250.0.
        y (float, optional): Y position in millimeters. Defaults to 150.0.

    Returns:
        QgsLayoutItemLabel: The created label item containing the credits.
    """
    label = ajouter_label(layout, text, x, y, font_name="Arial", font_size=7)
    label.attemptResize(QgsLayoutSize(40, 20, QgsUnitTypes.LayoutMillimeters))
    return label


# ──────────────────────────────────────────────
#  Legende
# ──────────────────────────────────────────────


def generate_legend_pdf_from_template(
    template_path: str,
    output_path: str,
    layer_names: list[str],
    logo_path: str | None = None,
    per_page: int = 25,
) -> str:
    """Generate a multi‑page legend PDF from a .qpt template.

    The function loads the given QPT layout, then creates a legend for the
    supplied *layer_names* on each page. Items such as the title, author and
    date are cloned from the template to preserve styling while ensuring each
    page has unique IDs. Long layer names are wrapped to avoid overflow.
    """
    # Load template layout
    project = QgsProject.instance()
    manager = project.layoutManager()
    layout_name = f"LegendFromTemplate_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    layout = create_layout(project, manager, layout_name)
    from qgis.core import QgsReadWriteContext
    from qgis.PyQt.QtXml import QDomDocument

    doc = QDomDocument()

    with open(template_path, encoding="utf-8") as f:
        doc.setContent(f.read())

    context = QgsReadWriteContext()

    layout.loadFromTemplate(
        doc,
        context,
        clearExisting=True,
    )

    # Retrieve template items (may be None if not present)
    legend_placeholder = layout.itemById("legend")
    title_template = layout.itemById("title")
    author_template = layout.itemById("author")
    date_template = layout.itemById("date")
    logo_template = layout.itemById("logo") if logo_path else None

    # Store placeholder position before removal
    if legend_placeholder:
        legend_x = legend_placeholder.pos().x()
        legend_y = legend_placeholder.pos().y()
        layout.removeLayoutItem(legend_placeholder)
        legend_placeholder = None
    else:
        legend_x = 30.0
        legend_y = 30.0

    # Determine page height for vertical offsets (A4 landscape)
    first_page = layout.pageCollection().page(0)
    page_height = first_page.pageSize().height() if first_page else 210.0

    # Chunk original layer names per page (no temporary renaming)
    chunks = list(_chunk_layers(layer_names, per_page))
    total_pages = len(chunks)

    for page_index, chunk in enumerate(chunks):
        # Add a new page for all but the first (template already provides one)
        if page_index > 0:
            new_page = QgsLayoutItemPage(layout)
            new_page.setPageSize(
                "A4",
                QgsLayoutItemPage.Orientation.Landscape,
            )
            layout.pageCollection().addPage(new_page)

        offset = page_index * page_height

        # Dummy map (invisible) required for legend linking
        dummy_map = _create_dummy_map(layout, QgsRectangle())

        # Build legend for this chunk
        legend = _make_legend(
            layout,
            dummy_map,
            x=legend_x,
            y=legend_y + offset,
            filter_by_extent=False,
        )
        # Set layer IDs explicitly using original layers
        layer_ids = []
        for name in chunk:
            layers = project.mapLayersByName(name)
            if layers:
                layer_ids.append(layers[0].id())
        if layer_ids:
            from qgis.core import QgsLayerTree

            root = QgsLayerTree()
            project = QgsProject.instance()
            for lid in layer_ids:
                layer = project.mapLayer(lid)
                if layer:
                    root.addLayer(layer)
            legend.model().setRootGroup(root)
            legend.setId(f"legend_{page_index}")
        # Title
        if title_template:
            title = QgsLayoutItemLabel(layout)
            title.setText(f"Légende ({page_index + 1}/{total_pages})")
            title.attemptMove(
                QgsLayoutPoint(
                    title_template.pos().x(),
                    title_template.pos().y() + offset,
                    QgsUnitTypes.LayoutMillimeters,
                )
            )
            title.setId(f"title_{page_index}")
            layout.addLayoutItem(title)

        # Author
        if author_template:
            author = QgsLayoutItemLabel(layout)
            author.setText("Auteur: QGIS User")
            author.attemptMove(
                QgsLayoutPoint(
                    author_template.pos().x(),
                    author_template.pos().y() + offset,
                    QgsUnitTypes.LayoutMillimeters,
                )
            )
            author.setId(f"author_{page_index}")
            layout.addLayoutItem(author)

        # Date
        if date_template:
            date_label = QgsLayoutItemLabel(layout)
            date_label.setText(datetime.now().strftime("%d/%m/%Y"))
            date_label.attemptMove(
                QgsLayoutPoint(
                    date_template.pos().x(),
                    date_template.pos().y() + offset,
                    QgsUnitTypes.LayoutMillimeters,
                )
            )
            date_label.setId(f"date_{page_index}")
            layout.addLayoutItem(date_label)

        # Logo (optional)
        if logo_template and logo_path:
            logo_item = QgsLayoutItemPicture(layout)
            logo_item.setPicturePath(logo_path)
            logo_item.attemptMove(
                QgsLayoutPoint(
                    logo_template.pos().x(),
                    logo_template.pos().y() + offset,
                    QgsUnitTypes.LayoutMillimeters,
                )
            )
            logo_item.attemptResize(
                QgsLayoutSize(
                    logo_template.rectWithFrame().width(),
                    logo_template.rectWithFrame().height(),
                    QgsUnitTypes.LayoutMillimeters,
                )
            )
            logo_item.setId(f"logo_{page_index}")
            layout.addLayoutItem(logo_item)

    # Export to PDF (layout cleanup handled by caller)
    try:
        _export_layout_to_pdf(layout, output_path)
    finally:
        manager.removeLayout(layout)

    return output_path


# ──────────────────────────────────────────────
#  Legende
# ──────────────────────────────────────────────


def _make_legend(
    layout,
    map_item,
    x=15.0,
    y=30.0,
    columns=2,
    filter_by_extent=True,
):
    legend = QgsLayoutItemLegend(layout)

    legend.setTitle("Légende")
    legend.setLinkedMap(map_item)

    if filter_by_extent:
        legend.setLegendFilterByMapEnabled(True)

    legend.setFrameEnabled(True)
    legend.setFrameStrokeWidth(QgsLayoutMeasurement(0.4))

    legend.setColumnCount(columns)
    legend.setColumnSpace(5)

    group_style = QgsLegendStyle()
    group_text = QgsTextFormat()
    group_text.setFont(QFont("Arial", 7, 1, False))
    group_style.setTextFormat(group_text)
    legend.setStyle(QgsLegendStyle.Group, group_style)

    label_style = QgsLegendStyle()
    label_text = QgsTextFormat()
    label_text.setFont(QFont("Arial", 6))
    label_style.setTextFormat(label_text)
    legend.setStyle(QgsLegendStyle.SymbolLabel, label_style)

    layout.addLayoutItem(legend)

    legend.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))   
    legend.refresh()

    return legend


def _chunk_layers(layer_names, per_page=25):
    for i in range(0, len(layer_names), per_page):
        yield layer_names[i : i + per_page]


def _create_dummy_map(layout, extent):
    map_item = QgsLayoutItemMap(layout)

    map_item.setRect(20, 20, 20, 20)
    map_item.setExtent(extent)

    layout.addLayoutItem(map_item)

    map_item.attemptResize(QgsLayoutSize(1, 1, QgsUnitTypes.LayoutMillimeters))

    map_item.attemptMove(QgsLayoutPoint(-100, -100, QgsUnitTypes.LayoutMillimeters))

    return map_item


def _add_legend_title(layout, page_index, total_pages):
    return add_title(
        layout,
        f"Légende ({page_index + 1}/{total_pages})",
        x=10,
        y=7,
        font_size=14,
    )


def _add_legend_fixed_items(
    layout,
    logo_path,
):
    add_logo(
        layout,
        logo_path,
        x=250,
        y=160,
    )

    add_copyright(
        layout,
        x=240,
        y=200,
        font_size=8,
    )


def _create_legend_page(
    layout,
    chunk,
    extent,
    logo_path,
    page_index,
    total_pages,
):
    page = QgsLayoutItemPage(layout)

    page.setPageSize(
        "A4",
        QgsLayoutItemPage.Orientation.Landscape,
    )

    layout.pageCollection().addPage(page)

    _add_legend_title(
        layout,
        page_index,
        total_pages,
    )

    map_item = _create_dummy_map(
        layout,
        extent,
    )

    _make_legend(
        layout,
        map_item,
        x=15,
        y=30,
        columns=2,
        filter_by_extent=True,
    )

    _add_legend_fixed_items(
        layout,
        logo_path,
    )


def _export_layout_to_pdf(layout, path):
    exporter = QgsLayoutExporter(layout)

    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = 300

    exporter.exportToPdf(path, settings)


def _export_separate_legend(
    directory,
    layer_names,
    date_hm,
    logo_path,
    per_page=25,
):
    """Export a separate legend PDF using the provided layer names.

    This function creates a multi‑page legend layout without any map items.
    It is used by the main PDF export workflow.
    """
    # Legacy function retained for compatibility; calls the newer implementation.
    return generate_legend_pdf_from_template(
        template_path=os.path.join(os.path.dirname(__file__), "../resources/simple_legend_layout.qpt"),
        output_path=os.path.join(directory, f"Legende_GeoPDF_{date_hm}.pdf"),
        layer_names=layer_names,
        logo_path=logo_path,
        per_page=per_page,
    )
