# -*- coding: utf-8 -*-
# Python 3

"""
Fonctions utilitaires pour la production de GeoPDF et éléments de mise en page QGIS.
Refactorisation du code d'origine de fonctions_lnstruction_ADS.py

Objectif : regrouper tout ce qui est relatif au GeoPDF dans une seule fonction
avec un minimum de paramètres, et factoriser les blocs répétés (échelle, flèche nord,
cadre, logo, copyright) en sous-fonctions réutilisables.
"""

import os
from datetime import datetime

from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QFont, QPolygonF
from qgis.PyQt.QtCore import QFile
from qgis.core import (
    QgsProject,
    QgsPrintLayout,
    QgsLayoutItemMap,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemScaleBar,
    QgsLayoutItemPicture,
    QgsLayoutItemPage,
    QgsLayoutItemPolyline,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLayoutMeasurement,
    QgsLayoutExporter,
    QgsLayerTree,
    QgsRectangle,
    QgsLegendStyle,
    QgsLineSymbol,
    QgsUnitTypes,
)
from qgis.utils import iface  # type: ignore


# ──────────────────────────────────────────────
#  Petit utilitaire de chemin vers les icônes
# ──────────────────────────────────────────────

def _icons_dir():
    """Renvoie le chemin absolu du sous-dossier icons/ du plugin."""
    basepath = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(basepath, "icons").replace("\\", "/")


def get_icon_path(icon_name):
    """Renvoie le chemin complet d'une icône si elle existe, sinon ''."""
    path = os.path.join(_icons_dir(), icon_name)
    return path if QFile.exists(path) else ""


# ──────────────────────────────────────────────
#  Fonction interne : rectangle QPolygonF
# ──────────────────────────────────────────────

def _make_rectangle_polygon(x1, y1, x2, y2):
    """Crée un QPolygonF rectangulaire fermé."""
    polygon = QPolygonF()
    polygon.append(QPointF(x1, y1))
    polygon.append(QPointF(x2, y1))
    polygon.append(QPointF(x2, y2))
    polygon.append(QPointF(x1, y2))
    polygon.append(QPointF(x1, y1))
    return polygon


def _style_cadre():
    """Renvoie un QgsLineSymbol pour les cadres de titre."""
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
#  Briques élémentaires de mise en page
# ──────────────────────────────────────────────

def ajouter_cadre_titre(layout, largeur_page=295.0):
    """Ajoute un cadre rectangulaire autour de la zone de titre (haut de page)."""
    polygon = _make_rectangle_polygon(2.0, 2.0, largeur_page, 25.0)
    polyline = QgsLayoutItemPolyline(polygon, layout)
    polyline.setSymbol(_style_cadre())
    layout.addLayoutItem(polyline)
    return polyline


def ajouter_titre(layout, texte, x=7.0, y=5.0,
                  font_name="Arial", font_size=13):
    """Ajoute un label de titre et ajuste sa taille au texte."""
    title = QgsLayoutItemLabel(layout)
    title.setText(texte)
    title.setFont(QFont(font_name, font_size))
    layout.addLayoutItem(title)
    title.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    title.adjustSizeToText()
    w = x + title.boundingRect().width()
    h = y + title.boundingRect().height()
    title.attemptResize(QgsLayoutSize(w, h))
    return title


def ajouter_echelle(layout, map_item, canvas_extent, x=5.0, y=195.0):
    """
    Ajoute une barre d'échelle adaptée automatiquement à l'étendue du canevas.
    Remplace le bloc dupliqué dans 3 fonctions du code d'origine.
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
        (100,   QgsUnitTypes.DistanceMeters,     "m",  25),
        (500,   QgsUnitTypes.DistanceMeters,     "m",  100),
        (1000,  QgsUnitTypes.DistanceMeters,     "m",  250),
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


def ajouter_fleche_nord(layout, x=275.0, y=4.0):
    """Ajoute la flèche Nord."""
    nord = QgsLayoutItemPicture(layout)
    path = get_icon_path("Nord.jpg")
    if path:
        nord.setPicturePath(path)
    layout.addLayoutItem(nord)
    nord.attemptResize(QgsLayoutSize(20, 20, QgsUnitTypes.LayoutMillimeters))
    nord.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return nord


def ajouter_logo(layout, x=255.0, y=165.0, taille=30.0,
                 icon_name="PREF_Cote_d_Or_CMJN_295_432px_Marianne.jpg"):
    """Ajoute le logo de la préfecture / DDT."""
    logo = QgsLayoutItemPicture(layout)
    path = get_icon_path(icon_name)
    if path:
        logo.setPicturePath(path)
    layout.addLayoutItem(logo)
    logo.attemptResize(QgsLayoutSize(taille, taille, QgsUnitTypes.LayoutMillimeters))
    logo.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return logo


def ajouter_copyright(layout, x=250.0, y=200.0,
                      organisme="DDT21", font_size=10):
    """Ajoute le label de copyright avec la date du jour."""
    date_str = datetime.strftime(datetime.now(), "%d/%m/%Y")
    label = QgsLayoutItemLabel(layout)
    label.setText("© {} le {}".format(organisme, date_str))
    label.setFont(QFont("Arial", font_size))
    label.adjustSizeToText()
    layout.addLayoutItem(label)
    label.attemptResize(QgsLayoutSize(40, 20, QgsUnitTypes.LayoutMillimeters))
    label.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return label


def ajouter_credits_fdp(layout, x=250.0, y=150.0):
    """Ajoute les crédits des fonds de plan IGN."""
    texte = (
        "Sources des fonds cartographiques:\n"
        "©IGN - PCI_EXPRESS - 2022\n"
        "©IGN - SCAN25® Version 1\n"
        "©IGN - BDORTHO® - PVA 2018"
    )
    label = QgsLayoutItemLabel(layout)
    label.setText(texte)
    label.setFont(QFont("Arial", 7))
    label.adjustSizeToText()
    layout.addLayoutItem(label)
    label.attemptResize(QgsLayoutSize(40, 20, QgsUnitTypes.LayoutMillimeters))
    label.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))
    return label


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


# ──────────────────────────────────────────────
#  Gestion de la visibilité des couches
# ──────────────────────────────────────────────

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


def allumer_couche(nom_couche, nom_groupe):
    """Rend une couche visible dans un groupe donné."""
    return _set_layer_visibility(nom_couche, nom_groupe, True)


def eteindre_couche(nom_couche, nom_groupe):
    """Rend une couche invisible dans un groupe donné."""
    return _set_layer_visibility(nom_couche, nom_groupe, False)


def eteindre_tous_les_groupes(noms_groupes):
    """Éteint toutes les couches de tous les groupes listés."""
    root = QgsProject.instance().layerTreeRoot()
    for nom in noms_groupes:
        groupe = root.findGroup(nom)
        if groupe is None:
            continue
        groupe.setItemVisibilityChecked(False)
        for child in groupe.children():
            child.setItemVisibilityChecked(False)


def allumer_couches_concernees(rapport, noms_groupes):
    """Allume les couches de zonage qui intersectent au moins une parcelle.

    rapport : dict avec rapport[key][5] = liste de noms de couches concernées.
    """
    root = QgsProject.instance().layerTreeRoot()
    for key in rapport:
        noms_couches_concernees = rapport[key][5]
        for nom_groupe in noms_groupes:
            groupe = root.findGroup(nom_groupe)
            if groupe is None:
                continue
            for child in groupe.children():
                if child.name() in noms_couches_concernees:
                    groupe.setItemVisibilityChecked(True)
                    child.setItemVisibilityChecked(True)


# ──────────────────────────────────────────────
#  Légende
# ──────────────────────────────────────────────

def _construire_legende(layout, map_item, noms_couches,
                        x=220.0, y=25.0, filtrer_par_emprise=True):
    """
    Construit une légende filtrée sur les couches listées.

    map_item doit être un QgsLayoutItemMap correctement configuré
    (avec une extent et ajouté au layout) pour que le filtrage fonctionne.

    Renvoie (legend, nb_items).
    """
    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("Legende")
    legend.setFrameEnabled(True)
    legend.setFrameStrokeWidth(QgsLayoutMeasurement(0.4))

    # Filtrer les couches du projet
    all_layers = QgsProject.instance().mapLayers().values()
    layers_to_add = [l for l in all_layers if l.name() in noms_couches]

    root = QgsLayerTree()
    for layer in layers_to_add:
        root.addLayer(layer)
    legend.model().setRootGroup(root)

    # Styles de police
    group_style = QgsLegendStyle()
    group_style.setFont(QFont("Arial", 7, 1, False))
    legend.setStyle(QgsLegendStyle.Group, group_style)

    label_style = QgsLegendStyle()
    label_style.setFont(QFont("Arial", 6, 1, False))
    legend.setStyle(QgsLegendStyle.SymbolLabel, label_style)

    # Lien avec la carte et filtrage spatial
    legend.setLinkedMap(map_item)
    if filtrer_par_emprise:
        legend.setLegendFilterByMapEnabled(True)
    legend.refresh()

    # Compter les items de légende
    nb_items = 0
    tree_view = iface.layerTreeView()
    model = tree_view.layerTreeModel()
    for layer in layers_to_add:
        layer_tree_node = model.rootGroup().findLayer(layer.id())
        if layer_tree_node:
            nb_items += len(model.layerLegendNodes(layer_tree_node))

    layout.addLayoutItem(legend)
    legend.setColumnSpace(35)
    legend.attemptMove(QgsLayoutPoint(x, y, QgsUnitTypes.LayoutMillimeters))

    return legend, nb_items


# ──────────────────────────────────────────────
#  Construction du titre
# ──────────────────────────────────────────────

def _construire_titre_rapport(rapport, max_parcelles=6):
    """Construit le titre du GeoPDF à partir des parcelles du rapport."""
    titre = "Rapport des parcelles :\n"
    noms = []
    for key in rapport:
        r = rapport[key]
        noms.append(
            "parcelle {}, section {}, feuille {}, commune {}".format(
                r[4], r[2], r[3], r[0]
            )
        )
    if len(noms) <= max_parcelles:
        titre += " ; ".join(noms)
    return titre


# ──────────────────────────────────────────────
#  Export légende séparée
# ──────────────────────────────────────────────

def _exporter_legende_separee(dossier, noms_couches, nb_items, date_hm):
    """
    Exporte la légende dans un PDF séparé dont la taille de page
    s'adapte au nombre d'items (A4, A3 ou A0).
    """
    project = QgsProject.instance()
    manager = project.layoutManager()

    layout_name = "Legende_GeoPDF_{}".format(date_hm)
    layout = creer_layout(project, manager, layout_name)

    # Choisir la taille de page selon le nombre d'items
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

    # Titre
    ajouter_titre(layout, "Ensemble des légendes du Géo-PDF :",
                  x=10, y=7, font_size=14)

    # On a besoin d'un map_item configuré pour que la légende puisse
    # filtrer par emprise. On le lie au canevas courant.
    # Le map_item doit être dans le layout pour que setLinkedMap fonctionne,
    # mais on le place hors de la zone visible (coordonnées négatives).
    map_item = QgsLayoutItemMap(layout)
    map_item.setRect(20, 20, 20, 20)
    canvas = iface.mapCanvas()
    map_item.setExtent(canvas.extent())
    layout.addLayoutItem(map_item)
    map_item.attemptResize(QgsLayoutSize(1, 1, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptMove(QgsLayoutPoint(-100, -100, QgsUnitTypes.LayoutMillimeters))

    # Légende
    legend, _ = _construire_legende(
        layout, map_item, noms_couches,
        x=15, y=30, filtrer_par_emprise=True
    )
    legend.setColumnCount(3)
    legend.setColumnSpace(5)

    # Habillage
    ajouter_logo(layout, x=x_logo, y=y_logo)
    ajouter_copyright(layout, x=x_date, y=y_date, font_size=8)

    # Export
    exporter = QgsLayoutExporter(layout)
    exporter.layout().refresh()

    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = 300

    nom_fichier = "Legende_GeoPDF_{}.pdf".format(date_hm)
    chemin = os.path.join(dossier, nom_fichier)
    exporter.exportToPdf(chemin, settings)

    # Nettoyage de ce layout uniquement (pas les autres)
    manager.removeLayout(layout)

    return chemin


# ══════════════════════════════════════════════
#  FONCTION PRINCIPALE : export GeoPDF complet
# ══════════════════════════════════════════════

def exporter_geopdf(rapport,
                    dossier_sortie,
                    groupes_a_interroger,
                    nom_raster_scan25="",
                    nom_raster_ortho="",
                    groupe_fonds_de_plan="Fonds de plan",
                    marge=600,
                    dpi=90,
                    seuil_legende_interne=12):
    """
    Produit un GeoPDF complet à partir du dictionnaire Rapport.

    Paramètres
    ----------
    rapport : dict
        Le dictionnaire Rapport issu de doInterrogation().
        Clef = Parcelle_id, valeur = liste de 12 éléments :
        [0] nom_commune, [1] insee, [2] code_section, [3] feuille,
        [4] num_parcelle, [5] liste_zonages_concernes, [6] geom_parcelle,
        [7] dico_attributs_zone_parcelle, [8] rect_impression [XMIN,YMIN,XMAX,YMAX],
        [9] couche_a_interroger, [10] dico_non_concernees, [11] rapport_name.
    dossier_sortie : str
        Chemin du dossier où écrire le fichier PDF.
    groupes_a_interroger : list of str
        Noms des groupes thématiques du projet QGIS.
    nom_raster_scan25 : str
        Nom de la couche Scan25 ('' pour ignorer).
    nom_raster_ortho : str
        Nom de la couche Orthophoto ('' pour ignorer).
    groupe_fonds_de_plan : str
        Nom du groupe contenant les fonds de plan raster.
    marge : int
        Marge en mètres autour de l'emprise des parcelles.
    dpi : int
        Résolution du PDF.
    seuil_legende_interne : int
        Au-delà de ce nombre d'items, la légende est exportée
        dans un PDF séparé.

    Retour
    ------
    tuple : (chemin_pdf, nb_items_legendes)
    """

    if not rapport:
        raise ValueError("Le dictionnaire rapport est vide, rien à exporter.")

    project = QgsProject.instance()
    manager = project.layoutManager()

    # ── 1. Calcul de l'emprise globale ──────────────────────────
    xmins, ymins, xmaxs, ymaxs = [], [], [], []
    noms_couches_concernees = set()

    for key in rapport:
        rect = rapport[key][8]
        xmins.append(rect[0])
        ymins.append(rect[1])
        xmaxs.append(rect[2])
        ymaxs.append(rect[3])
        for nom in rapport[key][5]:
            noms_couches_concernees.add(nom)

    emprise = QgsRectangle(
        min(xmins) - marge,
        min(ymins) - marge,
        max(xmaxs) + marge,
        max(ymaxs) + marge,
    )

    # ── 2. Titre ────────────────────────────────────────────────
    titre = _construire_titre_rapport(rapport)

    # ── 3. Gestion de la visibilité ─────────────────────────────
    eteindre_tous_les_groupes(groupes_a_interroger)
    allumer_couches_concernees(rapport, groupes_a_interroger)

    if nom_raster_scan25:
        allumer_couche(nom_raster_scan25, groupe_fonds_de_plan)
    if nom_raster_ortho:
        allumer_couche(nom_raster_ortho, groupe_fonds_de_plan)

    # Zoomer le canevas sur l'emprise
    canvas = iface.mapCanvas()
    canvas.setExtent(emprise)
    canvas.refresh()

    # ── 4. Création du layout ───────────────────────────────────
    date_hm = datetime.strftime(datetime.now(), "%Y_%m_%d_%Hh_%Mmin")
    layout_name = "GeoPDF_ADS_{}".format(date_hm)

    nettoyer_layouts(manager)
    layout = creer_layout(project, manager, layout_name)

    # Page A4 paysage (déjà créée par initializeDefaults)

    # ── 5. Carte ────────────────────────────────────────────────
    map_item = QgsLayoutItemMap(layout)
    map_item.setRect(20, 20, 20, 20)
    map_item.setExtent(emprise)
    map_item.attemptMove(QgsLayoutPoint(5, 26, QgsUnitTypes.LayoutMillimeters))
    map_item.attemptResize(QgsLayoutSize(240, 180, QgsUnitTypes.LayoutMillimeters))
    map_item.zoomToExtent(canvas.extent())
    layout.addLayoutItem(map_item)

    # ── 6. Éléments d'habillage ─────────────────────────────────
    ajouter_cadre_titre(layout, largeur_page=295.0)
    ajouter_titre(layout, titre)
    ajouter_echelle(layout, map_item, canvas.extent())
    ajouter_fleche_nord(layout)
    ajouter_credits_fdp(layout)
    ajouter_logo(layout)
    ajouter_copyright(layout)

    # ── 7. Légende ──────────────────────────────────────────────
    liste_couches = list(noms_couches_concernees)
    legend, nb_items = _construire_legende(layout, map_item, liste_couches)

    if nb_items >= seuil_legende_interne:
        # Trop d'items : retirer la légende du layout principal
        # et l'exporter dans un PDF séparé
        layout.removeLayoutItem(legend)
        _exporter_legende_separee(
            dossier_sortie, liste_couches, nb_items, date_hm
        )

    # ── 8. Export GeoPDF ────────────────────────────────────────
    exporter = QgsLayoutExporter(layout)
    exporter.layout().refresh()

    settings = QgsLayoutExporter.PdfExportSettings()
    settings.dpi = dpi
    settings.writeGeoPdf = True

    nom_fichier = "Rapport_cartographique_ADS_{}.pdf".format(date_hm)
    chemin_pdf = os.path.join(dossier_sortie, nom_fichier)
    exporter.exportToPdf(chemin_pdf, settings)

    # ── 9. Nettoyage ────────────────────────────────────────────
    nettoyer_layouts(manager)

    if nom_raster_scan25:
        eteindre_couche(nom_raster_scan25, groupe_fonds_de_plan)
    if nom_raster_ortho:
        eteindre_couche(nom_raster_ortho, groupe_fonds_de_plan)

    eteindre_tous_les_groupes(groupes_a_interroger)

    return chemin_pdf, nb_items
