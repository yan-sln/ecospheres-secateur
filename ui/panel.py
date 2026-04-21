import functools
import logging
import os

# Import using absolute path instead of relative
import sys
from typing import Any

from geoselector.core.exceptions import ApiError  # type: ignore
from qgis.core import (
    QgsLayerTreeGroup,
    QgsPalLayerSettings,
    QgsProject,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorLayerSimpleLabeling,
)  # noqa: UP035
from qgis.PyQt.QtCore import QStringListModel, Qt, QTimer  # noqa: UP035
from qgis.PyQt.QtGui import QFont  # noqa: UP035
from qgis.PyQt.QtWidgets import (  # noqa: UP035
    QComboBox,
    QCompleter,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from core.entities_selector import (
    fetch_entity_geometry,
    list_parcelles,
    list_sections,
    search_communes,
)


def handle_api_error(fallback: Any = None, update_ui: bool = True):
    """Catch ApiError, store state, optionally update UI, and return fallback."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Reset per-call state
            self._last_api_error_occurred = False
            self._last_api_error_retryable = False
            try:
                return func(self, *args, **kwargs)
            except ApiError as e:
                self._last_api_error_occurred = True
                self._last_api_error_retryable = getattr(e, "retryable", False)
                logging.exception(
                    "API error in %s args=%s kwargs=%s",
                    func.__name__,
                    args,
                    kwargs,
                )
                if update_ui:
                    try:
                        self.status_label.setText(e.to_user_friendly_message())
                    except Exception:
                        self.status_label.setText("Une erreur API est survenue.")
                return fallback

        return wrapper

    return decorator


class CadreurPanel(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Ecosphères Cadreur", iface.mainWindow())
        self.iface = iface
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._communes = []
        self._selected_code = None
        self._sections = []
        self._selected_section = None
        self._parcelles = []
        self._commune_name = None
        self._parcel_geom = None
        self._debounce_timer = QTimer(self)
        self._last_api_error_occurred: bool = False
        self._last_api_error_retryable: bool = False
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._do_search)

        self._build_ui()

    def _build_ui(self):
        # UI building as before

        container = QWidget()
        layout = QVBoxLayout(container)

        # Commune search
        layout.addWidget(QLabel("Commune :"))
        search_row = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tapez un nom de commune…")
        self.search_input.textChanged.connect(self._on_text_changed)

        self._completer_model = QStringListModel()
        self._completer = QCompleter(self._completer_model, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.activated[str].connect(self._on_commune_selected)
        self.search_input.setCompleter(self._completer)

        search_row.addWidget(self.search_input)
        layout.addLayout(search_row)

        # Section selector
        layout.addWidget(QLabel("Section :"))
        self.section_combo = QComboBox()
        self.section_combo.setEnabled(False)
        self.section_combo.currentIndexChanged.connect(self._on_section_selected)
        layout.addWidget(self.section_combo)

        # Buttons
        btn_row = QHBoxLayout()

        self.show_commune_button = QPushButton("Charger la commune")
        self.show_commune_button.setEnabled(False)
        self.show_commune_button.clicked.connect(self._on_show_commune)
        btn_row.addWidget(self.show_commune_button)

        self.show_sections_button = QPushButton("Charger les sections")
        self.show_sections_button.setEnabled(False)
        self.show_sections_button.clicked.connect(self._on_show_sections)
        btn_row.addWidget(self.show_sections_button)

        self.run_button = QPushButton("Charger les parcelles")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._on_show_parcels)
        btn_row.addWidget(self.run_button)

        layout.addLayout(btn_row)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Status
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setWidget(container)

    @handle_api_error(fallback=[], update_ui=True)
    def _search_communes(self, text: str) -> list:
        return search_communes(text)

    @handle_api_error(fallback=[], update_ui=True)
    def _fetch_sections(self, code: str) -> list:
        return list_sections(code)

    @handle_api_error(fallback=[], update_ui=True)
    def _fetch_parcelles(self, code: str, section: str) -> list:
        return list_parcelles(code, section)

    @handle_api_error(fallback=None, update_ui=False)
    def _get_geometry(self, entity):
        return fetch_entity_geometry(entity)

    def _on_text_changed(self, text):
        self._selected_code = None
        self.run_button.setEnabled(False)
        # Reset commune button when the user clears or changes the search
        self.show_commune_button.setEnabled(False)
        if len(text) >= 2:
            self._debounce_timer.start()
        else:
            self._completer_model.setStringList([])

    def _do_search(self):
        if self._selected_code:
            return
        text = self.search_input.text().strip()
        if len(text) < 2:
            return
        self._communes = self._search_communes(text)
        if self._last_api_error_occurred:
            return
        # Sort the commune objects themselves by name (case insensitive)
        self._communes.sort(key=lambda c: getattr(c, "name", "").lower())
        display = []
        for c in self._communes:
            name = getattr(c, "name", "")
            code = getattr(c, "code", "")
            display.append(f"{name} ({code})")
        self._completer_model.setStringList(display)
        # Show message when no results found
        if not self._communes:
            self.status_label.setText(f'Aucune commune trouvée pour "{text}"')
        else:
            self.status_label.setText("")
        self._completer.complete()

    def _on_commune_selected(self, text):
        # Find the matching commune and extract its data
        for c in self._communes:
            name = getattr(c, "name", "")
            code = getattr(c, "code", "")
            display = f"{name} ({code})"
            if display == text:
                self._selected_code = code
                self._commune_name = name

                # Reset downstream selections
                self._sections = []
                self._selected_section = None
                self.section_combo.clear()
                self.section_combo.setEnabled(False)
                self.section_combo.setCurrentIndex(-1)
                self._parcelles = []
                self.run_button.setEnabled(False)
                self.show_commune_button.setEnabled(True)
                self.status_label.setText(f"Commune sélectionnée : {self._commune_name} ({self._selected_code})")
                # Load sections for this commune
                self._load_sections()
                return

    def _load_sections(self):
        """Load sections for the currently selected commune and populate the combo box."""
        if not self._selected_code:
            return
        raw = self._fetch_sections(self._selected_code)
        if self._last_api_error_occurred:
            self._sections = []
            return
        # Deterministic deduplication using section identifier
        unique = {}
        for s in raw:
            key = getattr(s, "section", None)
            if key not in unique:
                unique[key] = s
        self._sections = list(unique.values())
        # Sort the section objects themselves by section identifier (case insensitive)
        self._sections.sort(key=lambda s: getattr(s, "section", "").lower())
        # Sections are now GeoEntity objects; use attribute access
        display = []
        for s in self._sections:
            # Show the section identifier ("section") in the UI
            display.append(str(s.section))
        self.section_combo.blockSignals(True)
        self.section_combo.clear()
        self.section_combo.addItems(display)
        self.section_combo.setEnabled(bool(display))
        self.section_combo.blockSignals(False)
        self.section_combo.setCurrentIndex(-1)
        # Enable the show sections button when sections are loaded
        self.show_sections_button.setEnabled(bool(display))
        # Update button text with count
        count = len(self._sections)
        self.show_sections_button.setText(f"Charger les sections ({count})")

    def _on_section_selected(self, index):
        """Handle user selection of a section."""
        if index < 0 or index >= len(self._sections):
            return
        sec = self._sections[index]
        self._selected_section = getattr(sec, "section", None)
        # Update status label to show selected section
        self.status_label.setText(f"Section sélectionnée : {self._selected_section}")
        # Enable run button immediately after section selection
        self.run_button.setEnabled(True)
        # Load parcels for this commune and section
        self._load_parcelles()

    def _on_show_sections(self):
        if not self._selected_code:
            return

        self.show_sections_button.setEnabled(False)
        self.status_label.setText("Récupération des géométries des sections…")
        self._force_repaint()

        # Get all sections for the selected commune
        if not self._sections:
            self.status_label.setText("Erreur : aucune section disponible.")
            self.show_sections_button.setEnabled(True)
            return

        missing = self._missing_section_layers()

        if not missing:
            self.status_label.setText("Toutes les sections sont déjà présentes.")
            self.show_sections_button.setEnabled(True)
            return

        sections_to_process = missing

        # Process all sections
        successful_layers = []
        failed_count = 0

        total_sections = len(sections_to_process)
        self._start_progress(total_sections)

        # Create a reusable symbol for section outlines
        from PyQt5.QtGui import QColor
        from qgis.core import (
            QgsSimpleLineSymbolLayer,
            QgsSingleSymbolRenderer,
            QgsSymbol,
            QgsWkbTypes,
        )

        section_symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PolygonGeometry)
        section_symbol.deleteSymbolLayer(0)  # Remove default fill layer

        # Create a line symbol layer with gray color and reasonable width
        line_layer = QgsSimpleLineSymbolLayer()
        line_layer.setWidth(0.26)  # Line width
        line_layer.setColor(QColor(199, 199, 199))  # Gray color

        # Add the line layer to the symbol
        section_symbol.appendSymbolLayer(line_layer)
        section_renderer = QgsSingleSymbolRenderer(section_symbol)

        had_error = False
        for i, section_obj in enumerate(sections_to_process):
            try:
                # Fetch geometry for this section
                geom = self._get_geometry(section_obj)
                if self._last_api_error_occurred:
                    had_error = True
                    section_num = getattr(section_obj, "section", "inconnue")
                    # API error for this section; will be reported after loop
                    failed_count += 1
                    self._update_progress(i, total_sections, f"Section {section_num} : erreur")
                    continue
                if geom is None or geom.isEmpty():
                    section_num = getattr(section_obj, "section", "inconnue")
                    self.status_label.setText(
                        f"Erreur : impossible de récupérer la géométrie de la section {section_num}."
                    )
                    failed_count += 1
                    self._update_progress(
                        i,
                        total_sections,
                        f"Section {getattr(section_obj, 'section', 'inconnue')} : erreur",
                    )
                    continue

                # Create a memory layer for this section
                from PyQt5.QtCore import QVariant
                from qgis.core import (
                    QgsFeature,
                    QgsField,
                    QgsVectorLayer,
                )

                # Create layer name using section number
                section_num = getattr(section_obj, "section", "")
                layer_name = (
                    f"Section {section_num}"
                    if section_num
                    else f"Section {getattr(section_obj, 'feature_id', 'inconnue')}"
                )

                # Create a memory layer for the section
                layer = QgsVectorLayer("Polygon?crs=EPSG:4326", layer_name, "memory")
                provider = layer.dataProvider()

                # Add fields for section information
                if provider is not None:
                    provider.addAttributes(
                        [
                            QgsField("commune_code", QVariant.String),
                            QgsField("section", QVariant.String),
                            QgsField("feature_id", QVariant.String),
                        ]
                    )
                    layer.updateFields()

                    # Create a feature with the geometry
                    feature = QgsFeature()
                    feature.setGeometry(geom)
                    feature.setAttributes(
                        [
                            self._selected_code,
                            getattr(section_obj, "section", ""),
                            getattr(section_obj, "feature_id", ""),
                        ]
                    )

                    # Add the feature to the layer
                    if provider.addFeature(feature):
                        # Apply the pre-created symbol to the layer
                        layer.setRenderer(section_renderer)

                        # Configure dynamic labeling for section number
                        layer_settings = QgsPalLayerSettings()
                        text_format = QgsTextFormat()

                        text_format.setFont(QFont("Arial", 8))
                        text_format.setSize(8)

                        buffer_settings = QgsTextBufferSettings()
                        buffer_settings.setEnabled(True)
                        buffer_settings.setSize(1)
                        buffer_settings.setColor(QColor("white"))

                        text_format.setBuffer(buffer_settings)
                        layer_settings.setFormat(text_format)

                        layer_settings.fieldName = "section"
                        layer_settings.placement = QgsPalLayerSettings.OverPoint

                        layer_settings.enabled = True

                        labeling = QgsVectorLayerSimpleLabeling(layer_settings)
                        layer.setLabelsEnabled(True)
                        layer.setLabeling(labeling)
                        layer.triggerRepaint()

                        successful_layers.append(layer)
                        self._update_progress(i, total_sections, f"Section {section_num} : ajoutée")
                    else:
                        self.status_label.setText(
                            f"Erreur : impossible d'ajouter la feature à la couche pour la section {section_num}."
                        )
                        failed_count += 1
                        self._update_progress(i, total_sections, f"Section {section_num} : erreur")
                else:
                    self.status_label.setText(
                        f"Erreur : impossible de créer le fournisseur de données pour la section {section_num}."
                    )
                    failed_count += 1
                    self._update_progress(i, total_sections, f"Section {section_num} : erreur")

            except Exception as e:
                self.status_label.setText(
                    f"Erreur lors du traitement de la section {getattr(section_obj, 'section', 'inconnue')} : {str(e)}"
                )
                failed_count += 1
                self._update_progress(
                    i,
                    total_sections,
                    f"Section {getattr(section_obj, 'section', 'inconnue')} : erreur",
                )

        # Group layers hierarchically by commune and sections
        if successful_layers:
            self._group_layers_by_commune_and_sections(successful_layers)

        # Add all layers to the project after grouping
        project = QgsProject.instance()
        if project and successful_layers:
            for layer in successful_layers:
                project.addMapLayer(layer, False)

        # Finish progress and update status
        if failed_count > 0:
            self._finish_progress(f"{len(successful_layers)} succès, {failed_count} erreurs")
        else:
            self._finish_progress("Succès complet")

        self.show_sections_button.setEnabled(True)

    def _on_show_commune(self):
        """Retrieve and display the geometry of the selected commune.
        The layer is added under a top‑level "Commune" group.
        """
        if not self._selected_code:
            return
        # Disable button while processing
        self.show_commune_button.setEnabled(False)
        self.status_label.setText("Récupération de la géométrie de la commune…")
        self._force_repaint()

        # Check if the commune layer already exists
        missing = self._missing_commune_layers()
        if not missing:
            self.status_label.setText("La géométrie de la commune est déjà affichée.")
            self.show_commune_button.setEnabled(True)
            return

        # Find the commune object corresponding to the selected code
        commune_obj = None
        for c in self._communes:
            if getattr(c, "code", "") == self._selected_code:
                commune_obj = c
                break
        if not commune_obj:
            self.status_label.setText("Erreur : données de la commune introuvables.")
            self.show_commune_button.setEnabled(True)
            return

        geom = self._get_geometry(commune_obj)
        if self._last_api_error_occurred:
            self.show_commune_button.setEnabled(True)
            return
        if geom is None or geom.isEmpty():
            self.status_label.setText("Erreur : impossible de récupérer la géométrie de la commune.")
            self.show_commune_button.setEnabled(True)
            return

        # Create a memory layer for the commune
        from PyQt5.QtCore import QVariant
        from qgis.core import QgsFeature, QgsField, QgsVectorLayer

        layer_name = f"{self._commune_name} ({self._selected_code})"
        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", layer_name, "memory")
        provider = layer.dataProvider()
        if provider is not None:
            provider.addAttributes(
                [
                    QgsField("commune_code", QVariant.String),
                    QgsField("nom", QVariant.String),
                ]
            )
            layer.updateFields()
            feature = QgsFeature()
            feature.setGeometry(geom)
            feature.setAttributes([self._selected_code, self._commune_name or ""])
            provider.addFeature(feature)

        # Symbol: transparent fill with gray outline
        from PyQt5.QtGui import QColor
        from qgis.core import QgsSimpleFillSymbolLayer, QgsSingleSymbolRenderer, QgsSymbol, QgsWkbTypes

        commune_symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PolygonGeometry)
        # Remove default layer(s)
        commune_symbol.deleteSymbolLayer(0)
        fill_layer = QgsSimpleFillSymbolLayer()
        fill_layer.setColor(QColor(255, 255, 255, 0))  # transparent fill
        fill_layer.setStrokeColor(QColor(199, 199, 199))
        fill_layer.setStrokeWidth(0.26)
        commune_symbol.appendSymbolLayer(fill_layer)
        renderer = QgsSingleSymbolRenderer(commune_symbol)
        layer.setRenderer(renderer)

        # Add layer to project and group
        self._group_layers_by_commune([layer])
        project = QgsProject.instance()
        if project:
            project.addMapLayer(layer, False)
            # Zoom to the newly added commune layer
            canvas = self.iface.mapCanvas()
            canvas.setExtent(layer.extent())
            canvas.refresh()

        self.status_label.setText("Géométrie de la commune affichée.")
        self.show_commune_button.setEnabled(True)

    def _load_parcelles(self):
        """Load parcels for the selected commune and section."""
        if not (self._selected_code and self._selected_section):
            return
        # Retrieve all parcels for the commune and section
        all_parcelles = self._fetch_parcelles(self._selected_code, self._selected_section)
        if self._last_api_error_occurred:
            self._parcelles = []
            return
        # Filter parcels to keep only those belonging to the selected section (safety net)
        self._parcelles = []
        for p in all_parcelles:
            if getattr(p, "section", None) == self._selected_section:
                self._parcelles.append(p)
        # Update button text with count
        count = len(all_parcelles)
        self.run_button.setText(f"Charger les parcelles ({count})")

    def _on_parcel_selected(self, index):
        """Handle user selection of a parcel and enable the run button."""
        if index < 0 or index >= len(self._parcelles):
            return
        parc = self._parcelles[index]
        parcel_id = getattr(parc, "feature_id", None)
        parcel_num = getattr(parc, "numero", "")
        self._selected_parcel = parcel_id
        self.run_button.setEnabled(True)
        # Show the parcel number (or fallback to id) in the status label
        display_num = parcel_num if parcel_num else str(parcel_id)
        self.status_label.setText(f"Parcelle sélectionnée : {display_num}")

    def _on_show_parcels(self):
        if not (self._selected_code and self._selected_section):
            return

        self.run_button.setEnabled(False)
        self.status_label.setText("Récupération des géométries des parcelles…")
        self._force_repaint()

        # Get all parcels in the selected section
        if not self._parcelles:
            self.status_label.setText("Erreur : aucune parcelle disponible.")
            self.run_button.setEnabled(True)
            return

        # Incremental filtre
        missing = self._missing_parcel_layers()

        if not missing:
            self.status_label.setText("Toutes les parcelles sont déjà présentes.")
            self.run_button.setEnabled(True)
            return

        # On ne traite QUE ce qui manque
        parcelles_to_process = missing

        # Process all parcels in the section
        successful_layers = []
        failed_count = 0

        total_parcelles = len(parcelles_to_process)
        self._start_progress(total_parcelles)

        # Create a reusable symbol for parcel outlines
        from PyQt5.QtGui import QColor
        from qgis.core import (
            QgsSimpleLineSymbolLayer,
            QgsSingleSymbolRenderer,
            QgsSymbol,
            QgsWkbTypes,
        )

        parcel_symbol = QgsSymbol.defaultSymbol(QgsWkbTypes.PolygonGeometry)
        parcel_symbol.deleteSymbolLayer(0)  # Remove default fill layer

        # Create a line symbol layer with gray color and reasonable width
        line_layer = QgsSimpleLineSymbolLayer()
        line_layer.setWidth(0.26)  # Line width
        line_layer.setColor(QColor(199, 199, 199))  # Gray color

        # Add the line layer to the symbol
        parcel_symbol.appendSymbolLayer(line_layer)
        parcel_renderer = QgsSingleSymbolRenderer(parcel_symbol)

        had_error = False
        for i, parcel_obj in enumerate(parcelles_to_process):
            try:
                # Fetch geometry for this parcel
                geom = self._get_geometry(parcel_obj)
                if self._last_api_error_occurred:
                    had_error = True
                    parcel_num = getattr(parcel_obj, "numero", "inconnue")
                    self.status_label.setText(f"Erreur API pour la parcelle {parcel_num}")
                    failed_count += 1
                    self._update_progress(i, total_parcelles, f"Parcelle {parcel_num} : erreur")
                    continue
                if geom is None or geom.isEmpty():
                    parcel_num = getattr(parcel_obj, "numero", "inconnue")
                    self.status_label.setText(
                        f"Erreur : impossible de récupérer la géométrie de la parcelle {parcel_num}."
                    )
                    failed_count += 1
                    self._update_progress(
                        i,
                        total_parcelles,
                        f"Parcelle {getattr(parcel_obj, 'numero', 'inconnue')} : erreur",
                    )
                    continue

                # Create a memory layer for this parcel
                from PyQt5.QtCore import QVariant
                from qgis.core import (
                    QgsFeature,
                    QgsField,
                    QgsVectorLayer,
                )

                # Create layer name using parcel number
                parcel_num = getattr(parcel_obj, "numero", "")
                layer_name = (
                    f"Parcelle {parcel_num}"
                    if parcel_num
                    else f"Parcelle {getattr(parcel_obj, 'feature_id', 'inconnue')}"
                )

                # Create a memory layer for the parcel
                layer = QgsVectorLayer("Polygon?crs=EPSG:4326", layer_name, "memory")
                provider = layer.dataProvider()

                # Add fields for parcel information
                if provider is not None:
                    provider.addAttributes(
                        [
                            QgsField("commune_code", QVariant.String),
                            QgsField("section", QVariant.String),
                            QgsField("numero", QVariant.String),
                            QgsField("feature_id", QVariant.String),
                        ]
                    )
                    layer.updateFields()

                    # Create a feature with the geometry
                    feature = QgsFeature()
                    feature.setGeometry(geom)
                    feature.setAttributes(
                        [
                            self._selected_code,
                            getattr(parcel_obj, "section", ""),
                            getattr(parcel_obj, "numero", ""),
                            getattr(parcel_obj, "feature_id", ""),
                        ]
                    )

                    # Add the feature to the layer
                    if provider.addFeature(feature):
                        # Apply the pre-created symbol to the layer
                        layer.setRenderer(parcel_renderer)

                        # Configure dynamic labeling for parcel number
                        layer_settings = QgsPalLayerSettings()
                        text_format = QgsTextFormat()

                        text_format.setFont(QFont("Arial", 8))
                        text_format.setSize(8)

                        buffer_settings = QgsTextBufferSettings()
                        buffer_settings.setEnabled(True)
                        buffer_settings.setSize(1)
                        buffer_settings.setColor(QColor("white"))

                        text_format.setBuffer(buffer_settings)
                        layer_settings.setFormat(text_format)

                        layer_settings.fieldName = "numero"
                        layer_settings.placement = QgsPalLayerSettings.OverPoint

                        layer_settings.enabled = True

                        labeling = QgsVectorLayerSimpleLabeling(layer_settings)
                        layer.setLabelsEnabled(True)
                        layer.setLabeling(labeling)
                        layer.triggerRepaint()

                        successful_layers.append(layer)
                        self._update_progress(i, total_parcelles, f"Parcelle {parcel_num} : ajoutée")
                    else:
                        self.status_label.setText(
                            f"Erreur : impossible d'ajouter la feature à la couche pour la parcelle {parcel_num}."
                        )
                        failed_count += 1
                        self._update_progress(i, total_parcelles, f"Parcelle {parcel_num} : erreur")
                else:
                    self.status_label.setText(
                        f"Erreur : impossible de créer le fournisseur de données pour la parcelle {parcel_num}."
                    )
                    failed_count += 1
                    self._update_progress(i, total_parcelles, f"Parcelle {parcel_num} : erreur")

            except Exception as e:
                self.status_label.setText(
                    f"Erreur lors du traitement de la parcelle {getattr(parcel_obj, 'numero', 'inconnue')} : {str(e)}"
                )
                failed_count += 1
                self._update_progress(
                    i,
                    total_parcelles,
                    f"Parcelle {getattr(parcel_obj, 'numero', 'inconnue')} : erreur",
                )

        # Group layers hierarchically after creation
        if successful_layers:
            self._group_layers_by_commune_and_section(successful_layers)

        # Add all layers to the project after grouping
        project = QgsProject.instance()
        if project and successful_layers:
            for layer in successful_layers:
                project.addMapLayer(layer, False)

        # Finish progress and update status
        if failed_count > 0:
            self._finish_progress(f"{len(successful_layers)} succès, {failed_count} erreurs")
        else:
            self._finish_progress("Succès complet")

        self.run_button.setEnabled(True)

    def _group_layers_by_commune_and_section(self, layers):
        """Group layers hierarchically by commune and section."""
        try:
            project = QgsProject.instance()
            if project:
                root = project.layerTreeRoot()
                if root:
                    # Get the section and commune info from the panel data
                    section_code = self._selected_section
                    commune_name = self._commune_name or "Commune inconnue"

                    # Create commune group if it doesn't exist
                    commune_group_name = commune_name
                    commune_group = None

                    # Look for existing commune group
                    for child in root.children() if root.children() else []:
                        if isinstance(child, QgsLayerTreeGroup) and child.name() == commune_group_name:
                            commune_group = child
                            break

                    # Create commune group if it doesn't exist
                    if not commune_group:
                        commune_group = root.addGroup(commune_group_name)

                    # Create section group inside commune group
                    section_group_name = f"Section {section_code}"
                    section_group = None

                    # Look for existing section group
                    if commune_group:
                        for child in commune_group.children() if commune_group.children() else []:
                            if isinstance(child, QgsLayerTreeGroup) and child.name() == section_group_name:
                                section_group = child
                                break

                    # Create section group if it doesn't exist
                    if not section_group and commune_group:
                        section_group = commune_group.addGroup(section_group_name)

                    # Move all layers to the section group
                    if section_group:
                        for layer in layers:
                            section_group.addLayer(layer)
        except Exception:
            # Silently ignore errors in grouping to prevent breaking the main functionality
            pass

    def _group_layers_by_commune_and_sections(self, layers):
        """Group layers hierarchically by commune and sections."""
        try:
            project = QgsProject.instance()
            if project:
                root = project.layerTreeRoot()
                if root:
                    # Get the commune info from the panel data
                    commune_name = self._commune_name or "Commune inconnue"

                    # Create commune group if it doesn't exist
                    commune_group_name = commune_name
                    commune_group = None

                    # Look for existing commune group
                    for child in root.children() if root.children() else []:
                        if isinstance(child, QgsLayerTreeGroup) and child.name() == commune_group_name:
                            commune_group = child
                            break

                    # Create commune group if it doesn't exist
                    if not commune_group:
                        commune_group = root.addGroup(commune_group_name)

                    # Create "Sections" group inside commune group
                    sections_group_name = "Sections"
                    sections_group = None

                    # Look for existing sections group
                    if commune_group:
                        for child in commune_group.children() if commune_group.children() else []:
                            if isinstance(child, QgsLayerTreeGroup) and child.name() == sections_group_name:
                                sections_group = child
                                break

                    # Create sections group if it doesn't exist
                    if not sections_group and commune_group:
                        sections_group = commune_group.addGroup(sections_group_name)

                    # Move all layers to the sections group
                    if sections_group:
                        for layer in layers:
                            sections_group.addLayer(layer)
        except Exception:
            # Silently ignore errors in grouping to prevent breaking the main functionality
            pass

    def _start_progress(self, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

    def _update_progress(self, current, total, text):
        self.progress_bar.setValue(current)
        self.status_label.setText(text)
        self._force_repaint()

    def _finish_progress(self, text):
        self.progress_bar.setVisible(False)
        self.status_label.setText(text)

    def _force_repaint(self):
        from qgis.PyQt.QtWidgets import QApplication  # noqa: UP035

        QApplication.processEvents()

    def _get_group_by_path(self, path):
        """
        path: list[str] → ex: ["Paris", "Sections"]
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

        return node

    def _missing_section_layers(self):
        path = [self._commune_name or "Commune inconnue", "Sections"]
        group = self._get_group_by_path(path)

        if not group:
            return self._sections  # tout manque

        existing = {child.name() for child in group.children() if not isinstance(child, QgsLayerTreeGroup)}

        missing = []
        for s in self._sections:
            section_num = getattr(s, "section", "")
            name = f"Section {section_num}" if section_num else f"Section {getattr(s, 'feature_id', 'inconnue')}"

            if name not in existing:
                missing.append(s)

        return missing

    def _missing_parcel_layers(self):
        path = [
            self._commune_name or "Commune inconnue",
            f"Section {self._selected_section}",
        ]
        group = self._get_group_by_path(path)

        if not group:
            return self._parcelles

        existing = {child.name() for child in group.children() if not isinstance(child, QgsLayerTreeGroup)}

        missing = []
        for p in self._parcelles:
            num = getattr(p, "numero", "")
            name = f"Parcelle {num}" if num else f"Parcelle {getattr(p, 'feature_id', 'inconnue')}"

            if name not in existing:
                missing.append(p)

        return missing

    def _missing_commune_layers(self):
        """Return a list containing the selected commune object if its layer is missing.
        The commune layer is stored under a top‑level group named "Communes".
        """
        # Locate the commune object matching the current selection
        commune_obj = None
        for c in self._communes:
            if getattr(c, "code", "") == self._selected_code:
                commune_obj = c
                break
        if not commune_obj:
            return []
        path = ["Communes"]
        group = self._get_group_by_path(path)
        # If the group does not exist, the layer is missing
        if not group:
            return [commune_obj]
        # Existing layer names under the group (ignore sub‑groups)
        existing = {child.name() for child in group.children() if not isinstance(child, QgsLayerTreeGroup)}
        expected_name = (
            f"{self._commune_name} ({self._selected_code})" if self._commune_name else f"{self._selected_code}"
        )
        if expected_name in existing:
            return []
        return [commune_obj]

    def _group_layers_by_commune(self, layers):
        """Group given layers under a top‑level "Commune" group.
        If the group does not exist, it is created.
        """
        try:
            project = QgsProject.instance()
            if not project:
                return
            root = project.layerTreeRoot()
            if not root:
                return
            # Ensure top‑level group "Communes"
            commune_group = None
            for child in root.children() if root.children() else []:
                if isinstance(child, QgsLayerTreeGroup) and child.name() == "Communes":
                    commune_group = child
                    break
            if not commune_group:
                commune_group = root.addGroup("Communes")
            # Add each layer to the group
            for layer in layers:
                commune_group.addLayer(layer)
        except Exception:
            pass
