from qgis.PyQt.QtCore import QStringListModel, Qt, QTimer  # noqa: UP035
from qgis.PyQt.QtWidgets import (  # noqa: UP035
    QComboBox,
    QCompleter,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.entities_selector import (
    clear_cache,
    fetch_parcel_geometry,
    list_parcelles,
    list_sections,
    search_communes,
)
from ..core.export import export_results_to_csv, export_results_to_pdf
from ..core.intersector import (
    add_results_to_project,
    find_wfs_layers,
    intersect_parcelle,
)


class SecateurPanel(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Ecosphères Secateur", parent or iface.mainWindow())
        self.iface = iface
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._communes = []
        self._selected_code = None
        self._sections = []
        self._selected_section = None
        self._parcelles = []
        self._selected_parcel = None
        self._result_layers = []
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

        # Parcelle selector
        layout.addWidget(QLabel("Parcelle :"))
        self.parcelle_combo = QComboBox()
        self.parcelle_combo.setEnabled(False)
        self.parcelle_combo.currentIndexChanged.connect(self._on_parcel_selected)
        layout.addWidget(self.parcelle_combo)

        # Buttons
        btn_row = QHBoxLayout()
        self.run_button = QPushButton("Interroger")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._on_run)
        btn_row.addWidget(self.run_button)

        self.clear_cache_button = QPushButton("Vider le cache")
        self.clear_cache_button.clicked.connect(self._on_clear_cache)
        btn_row.addWidget(self.clear_cache_button)

        self.export_csv_button = QPushButton("Exporter CSV")
        self.export_csv_button.setEnabled(False)
        self.export_csv_button.clicked.connect(self._on_export_csv)
        btn_row.addWidget(self.export_csv_button)

        self.export_pdf_button = QPushButton("Exporter PDF")
        self.export_pdf_button.setEnabled(False)
        self.export_pdf_button.clicked.connect(self._on_export_pdf)
        btn_row.addWidget(self.export_pdf_button)

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
            # Handle GeoEntity objects (no need for dict fallback anymore)
            name = getattr(c, "name", "")
            code = getattr(c, "code", "")
            display.append(f"{name} ({code})")
        self._completer_model.setStringList(display)
        self._completer.complete()

    def _on_commune_selected(self, text):
        # Find the matching commune and extract its data
        for c in self._communes:
            # Handle GeoEntity objects (no need for dict fallback anymore)
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
                self._selected_parcel = None
                self.parcelle_combo.clear()
                self.parcelle_combo.setEnabled(False)
                self.parcelle_combo.setCurrentIndex(-1)
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
        # Sort the section objects themselves by section identifier (case insensitive)
        self._sections.sort(key=lambda s: getattr(s, "section", "").lower())
        # Sections are now GeoEntity objects; use attribute access
        display = []
        for s in self._sections:
            # Handle GeoEntity objects (no need for dict fallback anymore)
            # Show the section identifier ("section") in the UI
            display.append(str(getattr(s, "section", "")))
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
        # Handle GeoEntity objects (no need for dict fallback anymore)
        self._selected_section = getattr(sec, "section", None)
        # Update status label to show selected section
        self.status_label.setText(f"Section sélectionnée : {self._selected_section}")
        # Reset parcel selection
        self._parcelles = []
        self._selected_parcel = None
        self.parcelle_combo.clear()
        self.parcelle_combo.setEnabled(False)
        self.parcelle_combo.setCurrentIndex(-1)
        self.run_button.setEnabled(False)
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
            # Handle GeoEntity objects (no need for dict fallback anymore)
            if getattr(p, "section", None) == self._selected_section:
                self._parcelles.append(p)
        # Sort the parcel objects themselves by parcel number (case insensitive)
        self._parcelles.sort(key=lambda p: getattr(p, "numero", "").lower())
        # Build display list using parcel number ("numero")
        display = []
        for p in self._parcelles:
            # Handle GeoEntity objects (no need for dict fallback anymore)
            display.append(str(getattr(p, "numero", "")))
        self.parcelle_combo.blockSignals(True)
        self.parcelle_combo.clear()
        self.parcelle_combo.addItems(display)
        self.parcelle_combo.setEnabled(bool(display))
        self.parcelle_combo.blockSignals(False)
        self.parcelle_combo.setCurrentIndex(-1)

    def _on_parcel_selected(self, index):
        """Handle user selection of a parcel and enable the run button."""
        if index < 0 or index >= len(self._parcelles):
            return
        parc = self._parcelles[index]
        # Handle GeoEntity objects (no need for dict fallback anymore)
        parcel_id = getattr(parc, "feature_id", None)
        parcel_num = getattr(parc, "numero", "")
        self._selected_parcel = parcel_id
        self.run_button.setEnabled(True)
        # Show the parcel number (or fallback to id) in the status label
        display_num = parcel_num if parcel_num else str(parcel_id)
        self.status_label.setText(f"Parcelle sélectionnée : {display_num}")

    def _on_run(self):
        if not (self._selected_code and self._selected_parcel):
            return

        self.run_button.setEnabled(False)
        self.status_label.setText("Récupération de la géométrie de la parcelle…")
        self._force_repaint()

        # Use the existing parcel object which already has service initialized
        # This avoids recreating the parcel and losing service initialization
        if not self._parcelles:
            self.status_label.setText("Erreur : aucune parcelle disponible.")
            self.run_button.setEnabled(True)
            return

        # Find the selected parcel object from our existing list
        parcel_obj = None
        for p in self._parcelles:
            if getattr(p, "feature_id", None) == self._selected_parcel:
                parcel_obj = p
                break

        if parcel_obj is None:
            self.status_label.setText("Erreur : parcelle non trouvée dans la liste.")
            self.run_button.setEnabled(True)
            return

        geom = fetch_parcel_geometry(parcel_obj)
        if geom is None or geom.isEmpty():
            self.status_label.setText("Erreur : impossible de récupérer la géométrie.")
            self.run_button.setEnabled(True)
            return

        self._parcel_geom = geom

        layers = find_wfs_layers()
        if not layers:
            self.status_label.setText("Aucune couche WFS trouvée dans le projet.")
            self.run_button.setEnabled(True)
            return

        self._start_progress(len(layers))
        self._update_progress(0, len(layers), f"Intersection avec {len(layers)} couche(s) WFS…")

        def progress(current, total, name):
            if current < total:
                self._update_progress(current, total, f"Intersection {current + 1}/{total} : {name}")

        results = intersect_parcelle(geom, layers, progress_callback=progress)

        if results:
            add_results_to_project(results)
            self._result_layers = results
            self.export_csv_button.setEnabled(True)
            self.export_pdf_button.setEnabled(True)
            total_feats = sum(r.featureCount() for r in results)
            self._finish_progress(f"Terminé — {total_feats} entité(s) trouvée(s) dans {len(results)} couche(s).")
        else:
            self._result_layers = []
            self.export_csv_button.setEnabled(False)
            self.export_pdf_button.setEnabled(False)
            self._finish_progress("Aucune intersection trouvée.")

        self.run_button.setEnabled(True)

    def _on_export_csv(self):
        if not self._result_layers:
            return
        folder = QFileDialog.getExistingDirectory(self, "Dossier d'export CSV")
        if not folder:
            return
        try:
            total = len(self._result_layers)
            self._start_progress(total)

            def progress(current, total, name):
                self._update_progress(current, total, f"Export CSV {current + 1}/{total} : {name}")

            written = export_results_to_csv(self._result_layers, folder, progress)
            self._finish_progress(f"Export CSV : {len(written)} fichier(s) dans {folder}")
        except Exception as e:
            self._finish_progress(f"Erreur export CSV : {e}")

    def _on_export_pdf(self):
        if not self._result_layers:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter le rapport PDF",
            "",
            "PDF (*.pdf)",
            options=QFileDialog.Options(),
        )
        if not path:
            return
        try:
            total = 1 + len(self._result_layers)
            self._start_progress(total)

            def progress(current, total, name):
                self._update_progress(current, total, f"Export PDF {current + 1}/{total} : {name}")

            if self._parcel_geom is None:
                self.status_label.setText("Erreur : géométrie de la parcelle non disponible pour l'export PDF.")
                self._finish_progress("Export PDF annulé : géométrie manquante.")
                return
            export_results_to_pdf(
                self._result_layers,
                self._commune_name or "",
                self._parcel_geom,
                path,
                progress_callback=progress,
            )
            self._finish_progress(f"Export PDF : {path}")
        except Exception as e:
            self._finish_progress(f"Erreur export PDF : {e}")

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
