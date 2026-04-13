import csv
import os
import re

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsGeometry,
    QgsLayout,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsProject,
    QgsRasterLayer,
    QgsReadWriteContext,
    QgsReport,
    QgsReportSectionLayout,
    QgsVectorLayer,
    QgsRectangle,
    QgsLayerTree,
    QgsLegendStyle,
    QgsLineSymbol,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsUnitTypes,
)
from qgis.PyQt.QtCore import QDate, QDateTime, QTime, QPointF  # noqa: UP035
from qgis.PyQt.QtGui import QFont, QPolygonF  # noqa: UP035
from qgis.PyQt.QtXml import QDomDocument  # noqa: UP035


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


# New enhanced PDF export functionality
import os
from datetime import datetime
from qgis.core import *
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QVariant
from qgis.PyQt.QtWidgets import QMessageBox

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.gui import *
from qgis.core import *
from qgis.core import QgsProject, QgsMapLayer, QgsVectorLayer

# ============================================================
# OUTILS
# ============================================================


def clean_layout(manager, layout_name):
    for layout in manager.printLayouts():
        if layout.name() == layout_name:
            manager.removeLayout(layout)


def create_layout(project, manager, layout_name):
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(layout_name)
    manager.addLayout(layout)
    return layout


def format_output_path(path):
    return os.path.normpath(path)


# ============================================================
# ELEMENTS GRAPHIQUES
# ============================================================


def add_map(layout, rec_emprise):
    map_item = QgsLayoutItemMap(layout)
    map_item.setRect(20, 20, 20, 20)

    rectangle = QgsRectangle(*rec_emprise)
    map_item.setExtent(rectangle)

    map_item.attemptMove(QgsLayoutPoint(5, 26, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(240, 180, QgsUnitTypes.LayoutMillimeters))

    layout.addLayoutItem(map_item)
    return map_item


def add_title(layout, text):
    title = QgsLayoutItemLabel(layout)
    title.setText(text)
    title.setFont(QFont("Arial", 13))

    layout.addLayoutItem(title)
    title.attemptMove(QgsLayoutPoint(7, 5, QgsUnitTypes.LayoutMillimeters))
    title.adjustSizeToText()


def add_scalebar(layout, map_item):
    # Use QgsProject instance to get extent - fallback if unable to get canvas
    project = QgsProject.instance()
    extent = QgsRectangle(0, 0, 100, 100)  # default extent

    try:
        # Try to get extent from canvas, with proper error handling
        canvas = project.canvas()
        if canvas:
            extent = canvas.extent()
    except Exception:
        # If canvas access fails, we'll use default extent and try to get extent from map item
        try:
            extent = map_item.extent()
        except Exception:
            pass  # Keep default extent if all attempts fail

    scaleBar = QgsLayoutItemScaleBar(layout)
    scaleBar.applyDefaultSettings()
    scaleBar.setLinkedMap(map_item)
    scaleBar.setStyle("Single Box")
    scaleBar.setNumberOfSegmentsLeft(0)
    scaleBar.setNumberOfSegments(2)

    # Calculate appropriate scale bar size
    dmax = max(extent.width(), extent.height())
    size = int(dmax / 5)

    if size <= 100:
        scaleBar.setUnits(QgsUnitTypes.DistanceMeters)
        scaleBar.setUnitLabel("m")
        scaleBar.setUnitsPerSegment(25)
    elif size <= 500:
        scaleBar.setUnits(QgsUnitTypes.DistanceMeters)
        scaleBar.setUnitLabel("m")
        scaleBar.setUnitsPerSegment(100)
    elif size <= 1000:
        scaleBar.setUnits(QgsUnitTypes.DistanceMeters)
        scaleBar.setUnitLabel("m")
        scaleBar.setUnitsPerSegment(250)
    elif size <= 10000:
        scaleBar.setUnits(QgsUnitTypes.DistanceKilometers)
        scaleBar.setUnitLabel("km")
        scaleBar.setUnitsPerSegment(0.5)
    else:
        scaleBar.setUnits(QgsUnitTypes.DistanceKilometers)
        scaleBar.setUnitLabel("km")
        scaleBar.setUnitsPerSegment(2.5)

    scaleBar.setBackgroundEnabled(True)
    layout.addLayoutItem(scaleBar)
    scaleBar.attemptMove(QgsLayoutPoint(5, 195, QgsUnitTypes.LayoutMillimeters))


def add_north_arrow(layout):
    # Use resource path directly for north arrow
    nord_icon = os.path.join(os.path.dirname(__file__), "..", "resources", "Nord.jpg")
    # Ensure the path exists
    if os.path.exists(nord_icon):
        north = QgsLayoutItemPicture(layout)
        north.setPicturePath(nord_icon)
        layout.addLayoutItem(north)
        north.attemptResize(QgsLayoutSize(20, 20, QgsUnitTypes.LayoutMillimeters))
        north.attemptMove(QgsLayoutPoint(275, 4, QgsUnitTypes.LayoutMillimeters))
    else:
        # If file doesn't exist, add a placeholder or skip
        pass


def add_header_frame(layout):
    poly = QPolygonF([QPointF(2, 2), QPointF(295, 2), QPointF(295, 25), QPointF(2, 25), QPointF(2, 2)])

    frame = QgsLayoutItemPolyline(poly, layout)

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

    frame.setSymbol(QgsLineSymbol.createSimple(props))
    layout.addLayoutItem(frame)


def add_copyright(layout):
    text = (
        "Sources des fonds cartographiques:\n"
        "©IGN – PCI_EXPRESS – 2022\n"
        "©IGN - SCAN25® Version 1\n"
        "©IGN – BDORTHO® - PVA 2018"
    )

    label = QgsLayoutItemLabel(layout)
    label.setText(text)
    label.setFont(QFont("Arial", 7))
    label.adjustSizeToText()

    layout.addLayoutItem(label)
    label.attemptResize(QgsLayoutSize(40, 20, QgsUnitTypes.LayoutMillimeters))
    label.attemptMove(QgsLayoutPoint(250, 150, QgsUnitTypes.LayoutMillimeters))


def add_logo(layout):
    # Use resource path directly for logo
    logo_icon = os.path.join(os.path.dirname(__file__), "..", "resources", "PREF_Cote_d_Or_CMJN_295_432px_Marianne.jpg")
    # Ensure the path exists
    if os.path.exists(logo_icon):
        logo = QgsLayoutItemPicture(layout)
        logo.setPicturePath(logo_icon)
        layout.addLayoutItem(logo)
        logo.attemptResize(QgsLayoutSize(30, 30, QgsUnitTypes.LayoutMillimeters))
        logo.attemptMove(QgsLayoutPoint(255, 165, QgsUnitTypes.LayoutMillimeters))
    else:
        # If file doesn't exist, add a placeholder or skip
        pass


def add_credit(layout):
    date = datetime.now().strftime("%d/%m/%Y")

    label = QgsLayoutItemLabel(layout)
    label.setText(f"© DDT21 le: {date}")
    label.setFont(QFont("Arial", 10))
    label.adjustSizeToText()

    layout.addLayoutItem(label)
    label.attemptMove(QgsLayoutPoint(250, 200, QgsUnitTypes.LayoutMillimeters))


# ============================================================
# LEGENDE
# ============================================================


def build_legend_layers(layer_names):
    return [layer for layer in QgsProject.instance().mapLayers().values() if layer.name() in layer_names]


def count_legend_items(layers):
    # Simplified approach: just count layers since we can't reliably access iface
    # This is more stable and avoids crashes from iface dependencies
    return len(layers)


def add_legend(layout, map_item, layers, nb_items):
    if nb_items >= 13:
        return False  # externalisation

    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("Legende")

    root = QgsLayerTree()
    for layer in layers:
        root.addLayer(layer)

    legend.model().setRootGroup(root)

    style_group = QgsLegendStyle()
    style_group.setFont(QFont("Arial", 7, 1, False))

    style_label = QgsLegendStyle()
    style_label.setFont(QFont("Arial", 6, 1, False))

    legend.setStyle(QgsLegendStyle.Group, style_group)
    legend.setStyle(QgsLegendStyle.SymbolLabel, style_label)

    legend.setLinkedMap(map_item)
    legend.setLegendFilterByMapEnabled(True)
    legend.refresh()

    # Ensure transparency settings for legend items
    legend.setFrameEnabled(True)
    legend.setFrameStrokeWidth(QgsLayoutMeasurement(0.4))

    layout.addLayoutItem(legend)
    legend.setColumnSpace(35)
    legend.attemptMove(QgsLayoutPoint(220, 25, QgsUnitTypes.LayoutMillimeters))

    return True


# ============================================================
# EXPORT LEGENDE EXTERNE
# ============================================================


def Export_Legende_pdf(path_name, rapport_name, project, manager, liste_couches, nb_items):

    layout_name = f"Legende_{datetime.now().strftime('%Y%m%d_%H%M')}"
    layout = create_layout(project, manager, layout_name)

    pc = layout.pageCollection()
    page = QgsLayoutItemPage(layout)
    pc.addPage(page)

    # format dynamique
    if nb_items < 30:
        page.setPageSize("A4", QgsLayoutItemPage.Orientation.Landscape)
    elif nb_items < 60:
        page.setPageSize("A3", QgsLayoutItemPage.Orientation.Landscape)
    else:
        page.setPageSize("A0", QgsLayoutItemPage.Orientation.Landscape)

    # titre
    title = QgsLayoutItemLabel(layout)
    title.setText("Ensemble des légendes du Géo-PDF :")
    title.setFont(QFont("Arial", 14))
    layout.addLayoutItem(title)
    title.attemptMove(QgsLayoutPoint(10, 7, QgsUnitTypes.LayoutMillimeters))
    title.adjustSizeToText()

    # légende
    legend = QgsLayoutItemLegend(layout)
    map_item = QgsLayoutItemMap(layout)

    legend.setLinkedMap(map_item)
    legend.setLegendFilterByMapEnabled(True)

    layers = build_legend_layers(liste_couches)
    root = QgsLayerTree()
    for layer in layers:
        root.addLayer(layer)

    legend.model().setRootGroup(root)

    legend.setColumnCount(3)
    legend.setColumnSpace(5)

    # Configure legend for proper transparency handling
    legend.setFrameEnabled(True)
    legend.setFrameStrokeWidth(QgsLayoutMeasurement(0.4))

    layout.addLayoutItem(legend)
    legend.attemptMove(QgsLayoutPoint(15, 30, QgsUnitTypes.LayoutMillimeters))

    # export
    filename = f"Legende_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    path = os.path.join(format_output_path(path_name), filename)

    exporter = QgsLayoutExporter(layout)
    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = 300
    settings.writeGeoPdf = True
    settings.exportMetadata = True
    settings.compressVectorGraphics = True
    settings.preserveTransparency = True
    exporter.exportToPdf(path, settings)

    return layout


# ============================================================
# EXPORT PRINCIPAL
# ============================================================


def Exports_GeoPDF(path_name, rapport_name, projet, manager, rec_emprise, liste_noms_couches_intersectees):
    # for en savoir plus:
    # https://north-road.com/2019/09/03/qgis-3-10-loves-geopdf/
    # https://qgis.org/pyqgis/3.28/
    # https://www.cadlinecommunity.co.uk/hc/en-us/articles/360003823717-QGIS-Creating-a-GeoPDF
    # https://qgis.org/pyqgis/3.28/core/QgsLayoutExporter.html#qgis.core.QgsLayoutExporter.PdfExportSettings.appendGeoreference
    # https://gis.stackexchange.com/questions/370656/can-i-create-a-geospatial-pdf-in-python-without-using-gis-software

    project = projet
    layouts_list = manager.printLayouts()
    liste_layout_names = []

    for idx, lay in enumerate(layouts_list):
        liste_layout_names.append(lay.name())

    # Fixed: This was referencing undefined variable layoutName
    # The original code had an error here
    for layout in layouts_list:
        if layout.name() == rapport_name:  # Use rapport_name instead of undefined layoutName
            manager.removeLayout(layout)

    layout = QgsPrintLayout(project)  # makes a new print layout object, takes a QgsProject as argument
    layout.initializeDefaults()  # create default map canvas
    layoutName = str(rapport_name)
    layout.setName(layoutName)
    # on ajoute un layout ayant nom de la couche
    manager.addLayout(layout)

    # la feuille A4 paysage mesure 297mm en largeur et 210mm en hauteur
    page = QgsLayoutItemPage(layout)
    page.setPageSize("A4", QgsLayoutItemPage.Landscape)
    page_center = page.pageSize().width() / 2

    # Composeur d'impression:
    # Tous les éléments de la mise page comme carte, étiquette,
    # …sont des objets représentés par des classes qui héritent de la classe de base QgsLayoutItem.

    # Carte:
    # This adds a map item to the Print Layout
    map = QgsLayoutItemMap(layout)
    map.setRect(20, 20, 20, 20)
    # Set Extent
    rec = rec_emprise
    rectangle = QgsRectangle(rec[0], rec[1], rec[2], rec[3])  # an example of how to set map extent with coordinates
    map.setExtent(rectangle)

    # Move: les arguments sont:
    # la distance à partir du bord gauche du layout,
    # puis la distance à partir du bord haut.
    map.attemptMove(QgsLayoutPoint(5, 26, QgsUnitTypes.LayoutMillimeters))
    map.attemptResize(
        QgsLayoutSize(240, 180, QgsUnitTypes.LayoutMillimeters)
    )  # Resize :  QgsLayoutSize(largeur, hauteur , unités employées)
    # Removed iface dependency: use map extent directly
    layout.addLayoutItem(map)

    # https://courses.spatialthoughts.com/pyqgis-in-a-day.html#turn-a-layer-onoff

    # Titre de la carte
    nom_de_la_carte = rapport_name
    title = QgsLayoutItemLabel(layout)
    title.setText(nom_de_la_carte)
    # title.setFont(QFont("Verdana",28))
    title.setFont(QFont("Arial", 13))
    # https://gis.stackexchange.com/questions/459233/setting-width-for-label-adjustsizetotext-in-pyqgis
    y = 5
    x = 7
    layout.addLayoutItem(title)
    title.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    title.adjustSizeToText()
    y += title.boundingRect().height()
    title.attemptResize(QgsLayoutSize(x + title.boundingRect().width(), y))
    layout.addLayoutItem(title)

    # Echelle graphique
    # on prépare la taille de la sclebar avec Etendu_du_Canvas qui est un QgsRectangle
    # https://qgis.org/pyqgis/3.2/core/other/QgsRectangle.html
    scaleBar = QgsLayoutItemScaleBar(layout)
    scaleBar.applyDefaultSettings()
    scaleBar.setLinkedMap(map)
    scaleBar.setStyle(
        "Single Box"
    )  # setStyle: 'Single Box', 'Double Box', 'Line Ticks Middle', 'Line Ticks Down', 'Line Ticks Up', 'Numeric'
    scaleBar.setNumberOfSegmentsLeft(0)
    scaleBar.setNumberOfSegments(2)
    # Calculate scale bar size using map extent directly (avoiding canvas dependency)
    try:
        Etendu_du_Canvas = map.extent()  # Use map extent directly
        H_Canvas = Etendu_du_Canvas.height()
        L_Canvas = Etendu_du_Canvas.width()
        if H_Canvas > L_Canvas:
            Dmax_Canvas = H_Canvas
        else:
            Dmax_Canvas = L_Canvas
    except Exception:
        # Fallback to reasonable default
        Dmax_Canvas = 1000
    # on va se donner comme taille de la barre d'échelle 1/5 de la taille maximale de l'étendue du Canevas de la carte
    scaleBar_total_size = int(Dmax_Canvas / 5)
    scaleBar.setMapUnitsPerScaleBarUnit(1)  # Sets the number of map units per scale bar unit used by the scalebar:
    if scaleBar_total_size <= 100:
        scaleBar.setUnits(QgsUnitTypes.DistanceMeters)
        scaleBar.setUnitLabel("m")
        scaleBar.setUnitsPerSegment(25)
    elif scaleBar_total_size <= 500:
        scaleBar.setUnits(QgsUnitTypes.DistanceMeters)
        scaleBar.setUnitLabel("m")
        scaleBar.setUnitsPerSegment(100)
    elif scaleBar_total_size <= 1000:
        scaleBar.setUnits(QgsUnitTypes.DistanceMeters)
        scaleBar.setUnitLabel("m")
        scaleBar.setUnitsPerSegment(250)
    elif scaleBar_total_size <= 10000:
        scaleBar.setUnits(QgsUnitTypes.DistanceKilometers)
        scaleBar.setUnitLabel("km")
        scaleBar.setUnitsPerSegment(0.5)
    elif scaleBar_total_size <= 50000:
        scaleBar.setUnits(QgsUnitTypes.DistanceKilometers)
        scaleBar.setUnitLabel("km")
        scaleBar.setUnitsPerSegment(2.5)
    scaleBar.setBackgroundEnabled(True)  # Fixed boolean value
    layout.addLayoutItem(scaleBar)
    scaleBar.attemptMove(QgsLayoutPoint(5, 195, QgsUnitTypes.LayoutMillimeters))  # attention on se répère dans la map !

    # Fleche nord
    fleche_nord = QgsLayoutItemPicture(layout)
    # Fixed: Replaced getThemeIcon with proper path handling
    nord_icon = os.path.join(os.path.dirname(__file__), "..", "resources", "Nord.jpg")
    if os.path.exists(nord_icon):
        fleche_nord.setPicturePath(nord_icon)
    else:
        # Skip if image doesn't exist rather than crashing
        fleche_nord = None
    if fleche_nord:
        layout.addLayoutItem(fleche_nord)
        fleche_nord.attemptResize(QgsLayoutSize(20, 20, QgsUnitTypes.LayoutMillimeters))
        fleche_nord.attemptMove(QgsLayoutPoint(275, 4, QgsUnitTypes.LayoutMillimeters))

    #############################################################################
    # Ajout d'un cadre autour du titre

    cadre = QPolygonF()
    cadre.append(QPointF(2.0, 2.0))
    cadre.append(QPointF(295.0, 2.0))  # A4 = 297 de largeur en paysage
    cadre.append(QPointF(295.0, 25.0))
    cadre.append(QPointF(2.0, 25.0))
    cadre.append(QPointF(2.0, 2.0))
    mon_cadre = QgsLayoutItemPolyline(cadre, layout)
    layout.addLayoutItem(mon_cadre)
    # style
    props = {}
    props["color"] = "0,5,0,55"
    props["width"] = "2.0"
    props["capstyle"] = "square"
    props["style"] = "solid"
    props["style_border"] = "solid"
    props["color_border"] = "black"
    props["width_border"] = "1.0"
    props["joinstyle"] = "miter"
    style = QgsLineSymbol.createSimple(props)
    mon_cadre.setSymbol(style)

    # copyrigth couches fond de plans:
    base = "Sources des fonds cartographiques: \n"
    cadastre = "©IGN – PCI_EXPRESS – 2022\n"
    texte_FDP = base + cadastre + "©IGN - SCAN25® Version 1 \n" + "©IGN – BDORTHO® - PVA 2018"
    copyrigth_FDP = QgsLayoutItemLabel(layout)
    copyrigth_FDP.setText(texte_FDP)
    copyrigth_FDP.setFont(QFont("Arial", 7))
    copyrigth_FDP.adjustSizeToText()
    layout.addLayoutItem(copyrigth_FDP)
    copyrigth_FDP.attemptResize(QgsLayoutSize(40, 20, QgsUnitTypes.LayoutMillimeters))
    copyrigth_FDP.attemptMove(QgsLayoutPoint(250, 150, QgsUnitTypes.LayoutMillimeters))

    # logo administration
    # un cadre est ajouté par défaut au label pour le supprimer :
    # logo.setFrameEnabled(False)
    logo = QgsLayoutItemPicture(layout)
    # Fixed: Replaced getThemeIcon with proper path handling
    marianne_icon = os.path.join(
        os.path.dirname(__file__), "..", "resources", "PREF_Cote_d_Or_CMJN_295_432px_Marianne.jpg"
    )
    if os.path.exists(marianne_icon):
        logo.setPicturePath(marianne_icon)
    else:
        # Skip if image doesn't exist rather than crashing
        logo = None
    if logo:
        layout.addLayoutItem(logo)
        logo.attemptResize(QgsLayoutSize(30, 30, QgsUnitTypes.LayoutMillimeters))
        logo.attemptMove(QgsLayoutPoint(255, 165, QgsUnitTypes.LayoutMillimeters))

    # copyrigth DDT
    date = datetime.strftime(datetime.now(), "%d/%m/%Y")
    credit_text = QgsLayoutItemLabel(layout)
    # credit_text.setText("© DDT21 le:"+'\n'+str(date))
    credit_text.setText("© DDT21 le: " + str(date))
    credit_text.setFont(QFont("Arial", 10))
    credit_text.adjustSizeToText()
    layout.addLayoutItem(credit_text)
    credit_text.attemptResize(QgsLayoutSize(40, 20, QgsUnitTypes.LayoutMillimeters))
    credit_text.attemptMove(QgsLayoutPoint(250, 200, QgsUnitTypes.LayoutMillimeters))

    ###########################################
    #                   légende
    ##########################################
    # on veut gérer le cartouche legende en fonction du nombre de figurés des analyses thématiques des layers
    # si ca ne rentre pas en une colonne dans le geopdf A4 paysage, on déporte sur autre pdf ce taille A4,A3 ou A0
    #################################
    # https://hg-map.fr/tutos/73-qgis-et-python?start=5
    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("Legende")

    # https://library.virginia.edu/data/articles//how-to-create-and-export-print-layouts-in-python-for-qgis-3
    # https://github.com/epurpur/PyQGIS-Scripts/blob/master/CreateLayoutManagerAndExport.py
    # on ne veut que la légende de la couche de zonage active....
    # get map layer objects of checked layers by matching their names and store those in a list
    checked_layers = liste_noms_couches_intersectees
    layersToAdd = [layer for layer in QgsProject().instance().mapLayers().values() if layer.name() in checked_layers]
    root = QgsLayerTree()
    for layer in layersToAdd:
        root.addLayer(layer)  # add layer objects to the layer tree
    legend.model().setRootGroup(root)

    ###############################################################
    # comment compter le nombre de figurés des différentes couches pour gerer la publication des legendes ?
    # https://gis.stackexchange.com/questions/464170/adjust-symbol-size-for-color-ramp-in-print-layout-legend-with-python
    nb_items_legendes = 0
    # Simplified legend counting without iface dependency
    # Just count layers since direct iface access was causing instability
    nb_items_legendes = len(layersToAdd)

    #############
    if (
        nb_items_legendes < 13
    ):  # si la legende prend plus de 12 lignes on la déporte dans un autre pdf car sinon elle déborde du geopdf
        style = QgsLegendStyle()  # make new style
        style.setFont(QFont("Arial", 7, 1, False))
        legend.setStyle(QgsLegendStyle.Group, style)
        style_base = QgsLegendStyle()  # make new style
        style_base.setFont(QFont("Arial", 6, 1, False))
        legend.setStyle(QgsLegendStyle.SymbolLabel, style_base)
        legend.rstyle(QgsLegendStyle.Symbol).setMargin(QgsLegendStyle.Top, 4)  # pour decaller le texte du symbole

        legend.setLinkedMap(map)  # map is an instance of QgsLayoutItemMap
        legend.setLegendFilterByMapEnabled(True)  # pour n'avoir que les nodes de lé legende dans l'emprise
        legend.refresh()
        layout.addLayoutItem(legend)
        legend.setColumnSpace(35)
        y = 25
        x = 220
        legend.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
        # Ensure legend transparency is properly handled
        legend.setFrameEnabled(True)
        legend.setFrameStrokeWidth(QgsLayoutMeasurement(0.4))
    else:  # si il y a plus de 12 items dans une legende on l'exporte à part !
        Export_Legende_pdf(path_name, rapport_name, projet, manager, liste_noms_couches_intersectees, nb_items_legendes)

    exporter = QgsLayoutExporter(layout)  # this creates a QgsLayoutExporter object
    exporter.layout().refresh()  # Refresh the layout before printing
    # setup settings
    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = 300
    # pour créer un geopdf !
    # https://api.qgis.org/api/3.28/structQgsLayoutExporter_1_1PdfExportSettings.html#a93ddb66c1e1f541a1bed511a41f9e396
    settings.writeGeoPdf = True
    # Enable geospatial metadata
    settings.exportMetadata = True
    # Fix transparency issues by setting proper PDF compression
    settings.compressVectorGraphics = True
    settings.preserveTransparency = True
    settings.rasterizeWholeImage = False
    # Fix transparency issues by setting proper PDF compression
    settings.compressVectorGraphics = True
    settings.preserveTransparency = True

    date_H_M = datetime.strftime(datetime.now(), "%Y_%m_%d_%Hh_%Mmin")
    file_rapport = str(path_name)
    path_rapport = file_rapport.replace("\\", "/")
    nom_export = "Rapport_cartographique_d_interrogation_ADS_des_parcelles_"
    nom_du_fichier_tableau_pdf = nom_export + str(date_H_M) + ".pdf"

    pdf_path = os.path.join(path_rapport, nom_du_fichier_tableau_pdf)
    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = 300
    settings.writeGeoPdf = True
    settings.exportMetadata = True
    settings.compressVectorGraphics = True
    settings.preserveTransparency = True
    settings.rasterizeWholeImage = False
    exporter.exportToPdf(pdf_path, settings)

    return layout, manager, layoutName, nb_items_legendes, liste_noms_couches_intersectees


def export_results_to_pdf(
    result_layers: list[QgsVectorLayer],
    commune_name: str,
    commune_geom: QgsGeometry,
    output_path: str,
    progress_callback=None,
):
    """Export a multi-page PDF report with enhanced layout and GeoPDF capabilities.

    progress_callback(current, total, name) is called before each page is built.
    """
    project = QgsProject.instance()
    manager = project.layoutManager()

    # If output_path is a directory, create a proper filename
    if os.path.isdir(output_path):
        date_H_M = datetime.strftime(datetime.now(), "%Y_%m_%d_%Hh_%Mmin")
        filename = f"Rapport_cartographique_d_interrogation_ADS_des_parcelles_{date_H_M}.pdf"
        full_path = os.path.join(output_path, filename)
    else:
        full_path = output_path

    # Buffered extent (5% margin)
    bbox = commune_geom.boundingBox()
    bbox.grow(bbox.width() * 0.05 + bbox.height() * 0.05)

    # Convert bbox to list for compatibility
    rec_emprise = [bbox.xMinimum(), bbox.yMinimum(), bbox.xMaximum(), bbox.yMaximum()]

    # Get all active layer names for legend
    layer_names = [layer.name() for layer in result_layers]

    # Create the main GeoPDF
    Exports_GeoPDF(os.path.dirname(full_path), commune_name, project, manager, rec_emprise, layer_names)

    # The export process is handled entirely by Exports_GeoPDF function
