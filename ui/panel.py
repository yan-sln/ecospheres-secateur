import os

# Import using absolute path instead of relative
import sys

from qgis.core import (
    QgsLayerTreeGroup,
    QgsProject,
    QgsPalLayerSettings,
    QgsTextFormat,
    QgsTextBufferSettings,
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
    clear_cache,
    fetch_parcel_geometry,
    list_parcelles,
    list_sections,
    search_communes,
)


class CadragePanel(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Ecosphères Cadrage", iface.mainWindow())
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
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._do_search)

        self._build_ui()

    def _build_ui(self):
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
        self.run_button = QPushButton("Interroger")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._on_run)
        btn_row.addWidget(self.run_button)

        self.clear_cache_button = QPushButton("Vider le cache")
        self.clear_cache_button.clicked.connect(self._on_clear_cache)
        btn_row.addWidget(self.clear_cache_button)

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

    def _on_text_changed(self, text):
        self._selected_code = None
        self.run_button.setEnabled(False)
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
        self._communes = search_communes(text)
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
                self.status_label.setText(f"Commune sélectionnée : {self._commune_name} ({self._selected_code})")
                # Load sections for this commune
                self._load_sections()
                return

    def _load_sections(self):
        """Load sections for the currently selected commune and populate the combo box."""
        if not self._selected_code:
            return
        self._sections = list_sections(self._selected_code)
        # Sections are now GeoEntity objects; use attribute access
        display = []
        for s in self._sections:
            # Show the section identifier ("section") in the UI
            display.append(str(s.section))
        # Sort the section objects themselves by section identifier (case insensitive)
        self._sections.sort(key=lambda s: getattr(s, "section", "").lower())
        self.section_combo.blockSignals(True)
        self.section_combo.clear()
        self.section_combo.addItems(display)
        self.section_combo.setEnabled(bool(display))
        self.section_combo.blockSignals(False)
        self.section_combo.setCurrentIndex(-1)

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

    def _load_parcelles(self):
        """Load parcels for the selected commune and section."""
        if not (self._selected_code and self._selected_section):
            return
        # Retrieve all parcels for the commune and section
        all_parcelles = list_parcelles(self._selected_code, self._selected_section)
        # Filter parcels to keep only those belonging to the selected section (safety net)
        self._parcelles = []
        for p in all_parcelles:
            if getattr(p, "section", None) == self._selected_section:
                self._parcelles.append(p)

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

    def _on_run(self):
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

        # Process all parcels in the section
        successful_layers = []
        failed_count = 0

        total_parcelles = len(self._parcelles)
        self._start_progress(total_parcelles)

        # Create a reusable symbol for parcel outlines
        from PyQt5.QtGui import QColor
        from qgis.core import (
            QgsSymbol,
            QgsSimpleLineSymbolLayer,
            QgsSingleSymbolRenderer,
            QgsWkbTypes,
            QgsPalLayerSettings,
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

        for i, parcel_obj in enumerate(self._parcelles):
            try:
                # Fetch geometry for this parcel
                geom = fetch_parcel_geometry(parcel_obj)
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
                    QgsProject,
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
        self._finish_progress(
            f"Traitement terminé : {len(successful_layers)} parcelle(s) traitée(s), {failed_count} échec(s)."
        )

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

    def _on_clear_cache(self):
        """Clear the cache of geoselector and update UI."""
        try:
            clear_cache()
            self.status_label.setText("Cache vidé avec succès.")
        except Exception as e:
            self.status_label.setText(f"Erreur lors du vidage du cache : {e}")

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
