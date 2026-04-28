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
    title = QgsLayoutItemLabel(layout)
    title.setText(texte)
    # Updated to use setTextFormat to avoid deprecation warning
    text_format = QgsTextFormat()
    text_format.setFont(QFont(font_name, font_size))
    title.setTextFormat(text_format)
    layout.addLayoutItem(title)
    title.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    title.adjustSizeToText()
    w = x + title.boundingRect().width()
    h = y + title.boundingRect().height()
    title.attemptResize(QgsLayoutSize(w, h))
    return title


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
        (100, QgsUnitTypes.DistanceMeters, "m", 25),
        (500, QgsUnitTypes.DistanceMeters, "m", 100),
        (1000, QgsUnitTypes.DistanceMeters, "m", 250),
        (10000, QgsUnitTypes.DistanceKilometers, "km", 0.5),
        (50000, QgsUnitTypes.DistanceKilometers, "km", 2.5),
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


def add_logo(layout, x=255.0, y=165.0, taille=30.0, icon_name="PREF_Cote_d_Or_CMJN_295_432px_Marianne.jpg"):
    """Add the prefecture/DDT logo picture to the layout.

    Parameters:
        layout (QgsLayout): The layout to modify.
        x (float, optional): X position in millimeters. Defaults to 255.0.
        y (float, optional): Y position in millimeters. Defaults to 165.0.
        taille (float, optional): Size of the logo in millimeters (both width and height). Defaults to 30.0.
        icon_name (str, optional): Filename of the logo icon. Defaults to "PREF_Cote_d_Or_CMJN_295_432px_Marianne.jpg".

    Returns:
        QgsLayoutItemPicture: The picture item representing the logo.
    """
    logo = QgsLayoutItemPicture(layout)
    path = get_icon_path(icon_name)
    if path:
        logo.setPicturePath(path)
    layout.addLayoutItem(logo)
    logo.attemptResize(QgsLayoutSize(taille, taille, QgsUnitTypes.LayoutMillimeters))
    logo.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return logo


def add_copyright(layout, x=250.0, y=200.0, organisme="DDT21", font_size=10):
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
    label = QgsLayoutItemLabel(layout)
    label.setText(f"© {organisme} le {date_str}")
    text_format = QgsTextFormat()
    text_format.setFont(QFont("Arial", font_size))
    label.setTextFormat(text_format)
    label.adjustSizeToText()
    layout.addLayoutItem(label)
    label.attemptResize(QgsLayoutSize(40, 20, QgsUnitTypes.LayoutMillimeters))
    label.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return label


def add_map_credits(layout, x=250.0, y=150.0):
    """Add the credits for IGN map sources.

    Parameters:
        layout (QgsLayout): The layout to modify.
        x (float, optional): X position in millimeters. Defaults to 250.0.
        y (float, optional): Y position in millimeters. Defaults to 150.0.

    Returns:
        QgsLayoutItemLabel: The created label item containing the credits.
    """
    texte = (
        "Sources des fonds cartographiques:\n"
        "©IGN - PCI_EXPRESS - 2022\n"
        "©IGN - SCAN25® Version 1\n"
        "©IGN - BDORTHO® - PVA 2018"
    )
    label = QgsLayoutItemLabel(layout)
    label.setText(texte)
    # Updated to use setTextFormat to avoid deprecation warning
    text_format = QgsTextFormat()
    text_format.setFont(QFont("Arial", 7))
    label.setTextFormat(text_format)
    label.adjustSizeToText()
    layout.addLayoutItem(label)
    label.attemptResize(QgsLayoutSize(40, 20, QgsUnitTypes.LayoutMillimeters))
    label.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return label


# ──────────────────────────────────────────────
#  Legende
# ──────────────────────────────────────────────


def _make_legend(layout, map_item, noms_couches, x=220.0, y=25.0, filtrer_par_emprise=True):
    """Construct a filtered legend for the listed layers.

    Parameters:
        layout (QgsLayout): The layout to modify.
        map_item (QgsLayoutItemMap): The map item correctly configured (with extent and added to the layout) for filtering to work.
        noms_couches (list of str): Names of layers to include.
        x (float, optional): X position in millimeters. Defaults to 220.0.
        y (float, optional): Y position in millimeters. Defaults to 25.0.
        filtrer_par_emprise (bool, optional): Whether to filter by map extent. Defaults to True.

    Returns:
        tuple: (legend, nb_items) where legend is the QgsLayoutItemLegend and nb_items is the count of legend items.
    """
    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("Legende")
    legend.setFrameEnabled(True)
    legend.setFrameStrokeWidth(QgsLayoutMeasurement(0.4))

    # Filtrer les couches du projet
    all_layers = QgsProject.instance().mapLayers().values()
    layers_to_add = [l for l in all_layers if l.name() in noms_couches]

    # Styles de police
    group_style = QgsLegendStyle()
    # Updated to use setTextFormat to avoid deprecation warning
    group_text_format = QgsTextFormat()
    group_text_format.setFont(QFont("Arial", 7, 1, False))
    group_style.setTextFormat(group_text_format)
    legend.setStyle(QgsLegendStyle.Group, group_style)

    label_style = QgsLegendStyle()
    # Updated to use setTextFormat to avoid deprecation warning
    label_text_format = QgsTextFormat()
    label_text_format.setFont(QFont("Arial", 6, 1, False))
    label_style.setTextFormat(label_text_format)
    legend.setStyle(QgsLegendStyle.SymbolLabel, label_style)

    # Lien avec la carte et filtrage spatial
    legend.setLinkedMap(map_item)
    if filtrer_par_emprise:
        legend.setLegendFilterByMapEnabled(True)
    legend.refresh()

    # Compter les items de légende
    nb_items = 0
    for layer in layers_to_add:
        renderer = layer.renderer()
        if renderer is None:
            nb_items += 1
        elif hasattr(renderer, "categories"):  # categorized
            nb_items += len(renderer.categories())
        elif hasattr(renderer, "ranges"):  # graduated
            nb_items += len(renderer.ranges())
        elif hasattr(renderer, "rules"):  # rule-based
            nb_items += len(renderer.rootRule().children())
        else:
            nb_items += 1

    layout.addLayoutItem(legend)
    legend.setColumnSpace(35)
    legend.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))

    return legend, nb_items


def _export_separate_legend(dossier, noms_couches, nb_items, date_hm, extent):
    """Export the legend to a separate PDF with page size adapting to the number of items (A4, A3, or A0).

    Parameters:
        dossier (str): Output directory path.
        noms_couches (list of str): Layer names to include in the legend.
        nb_items (int): Number of legend items, used to choose page size.
        date_hm (str): Date and hour string for naming the file.
        extent (QgsRectangle): Extent for a temporary map item required for filtering.

    Returns:
        str: Full path to the exported PDF file.
    """
    project = QgsProject.instance()
    manager = project.layoutManager()

    layout_name = f"Legende_GeoPDF_{date_hm}"
    layout = create_layout(project, manager, layout_name)

    # Choose page size from number of items
    if nb_items < 30:
        page_format = "A4"
        orientation = QgsLayoutItemPage.Orientation.Landscape
        x_logo, y_logo = 260, 160
        x_date, y_date = 250, 20
    elif nb_items < 60:
        page_format = "A3"
        orientation = QgsLayoutItemPage.Orientation.Landscape
        x_logo, y_logo = 390, 260
        x_date, y_date = 370, 20
    else:
        page_format = "A0"
        orientation = QgsLayoutItemPage.Orientation.Landscape
        x_logo, y_logo = 1159, 800
        x_date, y_date = 1140, 20

    pc = layout.pageCollection()
    page = QgsLayoutItemPage(layout)
    page.setPageSize(page_format, orientation)
    pc.addPage(page)
    pc.page(0).setPageSize(page_format, orientation)

    # Title
    add_title(layout, "Ensemble des légendes du Géo-PDF :", x=10, y=7, font_size=14)

    # We need a map_item configured so that the legend can
    # filter by footprint. We link it to the current canvas.
    # The map_item must be within the layout for setLinkedMap to work,
    # but we place it outside the visible area (negative coordinates).
    map_item = QgsLayoutItemMap(layout)
    map_item.setRect(20, 20, 20, 20)
    map_item.setExtent(extent)
    layout.addLayoutItem(map_item)
    map_item.attemptResize(QgsLayoutSize(1, 1, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptMove(QgsLayoutPoint(-100, -100, QgsUnitTypes.LayoutMillimeters))

    # Legend
    legend, _ = _make_legend(layout, map_item, noms_couches, x=15, y=30, filtrer_par_emprise=True)
    legend.setColumnCount(3)
    legend.setColumnSpace(5)

    # Element
    add_logo(layout, x=x_logo, y=y_logo)
    add_copyright(layout, x=x_date, y=y_date, font_size=8)

    # Export
    exporter = QgsLayoutExporter(layout)
    exporter.layout().refresh()

    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = 300

    nom_fichier = f"Legende_GeoPDF_{date_hm}.pdf"
    chemin = os.path.join(dossier, nom_fichier)
    exporter.exportToPdf(chemin, settings)

    # Clean only this layout
    manager.removeLayout(layout)

    return chemin
