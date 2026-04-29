from qgis.core import QgsFeature, QgsMapLayerProxyModel, QgsProject, QgsVectorLayer, QgsWkbTypes, QgsProcessingFeedback
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.export import export_results_to_csv, export_results_to_pdf
from ..core.intersector import add_results_to_project, intersect_layer
from ..core.logger import logger
from ..core.utils import find_layers, get_created_objects_group, get_results_group


class SecateurPanel(QDockWidget):
    # Added state for basemap handling
    _selected_basemap = None
    _basemap_layers = []

    def __init__(self, iface, parent=None):
        super().__init__("Ecosphères Secateur", parent or iface.mainWindow())
        self.iface = iface

        self._layers = []
        self._selected_layer = None
        self._result_layers = []

        self._build_ui()
        self._load_layers()

    # ──────────────────────────────────────────────
    #  UI construction
    # ──────────────────────────────────────────────

    def _build_ui(self):
        # Build the UI with source layer selector, run button, CSV export, basemap selector, and PDF export
        container = QWidget()
        layout = QVBoxLayout(container)

        #
        layout.addWidget(QLabel("Sélectionner l'objet à intersecter :"))

        # Row with button only
        btn_row = QHBoxLayout()
        self.run_button = QPushButton("Utiliser la géométrie active")
        self.run_button.setEnabled(True)
        self.run_button.clicked.connect(self._execute)
        btn_row.addWidget(self.run_button)
        # Cancel button placeholder – future hook for processing feedback cancellation
        # self.cancel_button = QPushButton("Annuler")
        # self.cancel_button.setEnabled(False)
        # self.cancel_button.clicked.connect(self._cancel_feedback)
        # btn_row.addWidget(self.cancel_button)
        layout.addLayout(btn_row)

        # Basemap selector
        layout.addWidget(QLabel("Fond de carte :"))
        self.basemap_combo = QgsMapLayerComboBox()
        self.basemap_combo.setFilters(QgsMapLayerProxyModel.RasterLayer)  # type: ignore
        self.basemap_combo.layerChanged.connect(self._on_basemap_selected)  # type: ignore
        layout.addWidget(self.basemap_combo)

        export_row = QHBoxLayout()
        self.export_csv_button = QPushButton("Exporter CSV")
        self.export_csv_button.setEnabled(False)
        self.export_csv_button.clicked.connect(self._on_export_csv)
        export_row.addWidget(self.export_csv_button)

        self.export_pdf_button = QPushButton("Exporter PDF")
        self.export_pdf_button.setEnabled(False)
        self.export_pdf_button.clicked.connect(self._on_export_pdf)
        export_row.addWidget(self.export_pdf_button)
        layout.addLayout(export_row)

        self.progress_bar = QProgressBar()
        # Cancel button placeholder – future hook for processing cancellation
        # self.cancel_button = QPushButton("Annuler")
        # self.cancel_button.setEnabled(False)
        # self.cancel_button.clicked.connect(self._cancel_feedback)
        self._feedback = None
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setWidget(container)

    # ──────────────────────────────────────────────
    #  Button utilities
    # ──────────────────────────────────────────────

    def _set_export_enabled(self, csv: bool | None = None, pdf: bool | None = None) -> None:
        """Enable/disable export buttons.
        Pass None to leave a button unchanged.
        """
        if csv is not None:
            self.export_csv_button.setEnabled(csv)
        if pdf is not None:
            self.export_pdf_button.setEnabled(pdf)

    # ──────────────────────────────────────────────
    #  Layer utilities
    # ──────────────────────────────────────────────

    def _load_layers(self):
        # Load vector layers for source selection
        self._layers = [L for L in QgsProject.instance().mapLayers().values() if isinstance(L, QgsVectorLayer)]
        # Load all layers (vector + raster) for basemap selection
        self._all_layers = list(QgsProject.instance().mapLayers().values())

    def _on_basemap_selected(self, layer):
        if layer is None:
            self._selected_basemap = None
            self._set_status("Fond de carte non sélectionné.", level="warning")
            self._set_export_enabled(csv=None, pdf=False)
            return

        self._selected_basemap = layer
        self._set_status(f"Fond de carte sélectionné : {layer.name()}", level="info")
        self._set_export_enabled(csv=None, pdf=True)

    def _prepare_source_layer(self) -> QgsVectorLayer | None:
        """Return the active vector layer or None with a status message.

        If the active item is not a vector layer (e.g., a group) or no active layer, the
        selection is reset and a warning is shown.
        """
        self._selected_layer = None
        self._selected_feature = None
        layer = self.iface.activeLayer()
        if layer is None:
            self._set_status("Aucune entité active.", level="warning")
            return None
        if not isinstance(layer, QgsVectorLayer):
            self._set_status("Sélection réinitialisée (pas de couche vectorielle).", level="warning")
            return None
        # Reject layers that belong to the "Résultats secateur" group
        results_group = get_results_group()
        if results_group.findLayer(layer.id()) is not None:
            self._set_status("La sélection appartient au groupe Résultats.", level="warning")
            return None
        return layer

    def _create_memory_layer_from_feature(self, source_layer: QgsVectorLayer, feature: QgsFeature) -> QgsVectorLayer:
        """Create (or replace) a memory layer containing *feature*.

        The layer is added to the project (not inserted in any group).
        """
        layer_name = f"{source_layer.name()}_feature_{feature.id()}"
        project = QgsProject.instance()
        # Remove any existing memory layer with the same name
        for lyr in project.mapLayersByName(layer_name):
            project.removeMapLayer(lyr)
        # Determine geometry type string for memory provider
        geom_type = QgsWkbTypes.displayString(source_layer.wkbType())
        mem_layer = QgsVectorLayer(
            f"{geom_type}?crs={source_layer.crs().authid()}",
            layer_name,
            "memory",
        )
        # Copy fields
        mem_layer.dataProvider().addAttributes(source_layer.fields())
        mem_layer.updateFields()
        # Clone the feature
        new_feat = QgsFeature()
        new_feat.setGeometry(feature.geometry())
        new_feat.setAttributes(feature.attributes())
        mem_layer.dataProvider().addFeature(new_feat)
        mem_layer.updateExtents()
        # Add to project without adding to the layer tree root
        project.addMapLayer(mem_layer, False)
        return mem_layer

    def _use_active_layer_or_feature(self):
        """Orchestrate selection of a layer or a single feature.

        Uses ``_prepare_source_layer`` and ``_create_memory_layer_from_feature``
        to keep the logic pure and side‑effects limited.
        """
        layer = self._prepare_source_layer()
        if layer is None:
            return
        selected = layer.selectedFeatures()
        if len(selected) == 1:
            mem_layer = self._create_memory_layer_from_feature(layer, selected[0])
            # Insert the memory layer into the "Objets créés" group as before
            group = get_created_objects_group()
            group.insertLayer(-1, mem_layer)
            self._selected_layer = mem_layer
            self._selected_feature = selected[0]
        elif len(selected) > 1:
            self._selected_layer = layer
            self._selected_feature = None
            self._set_status("Plusieurs objets sélectionnés !", level="warning")
        else:
            self._selected_layer = layer
            self._selected_feature = None
            self._set_status(f"Couche sélectionnée : {layer.name()}", level="info")

    def _execute(self):
        """Orchestrate active geometry selection then run the intersection with error handling."""
        self._use_active_layer_or_feature()
        if self._selected_layer is None:
            return
        try:
            self._on_run()
        except Exception as e:
            self._set_status(f"Erreur d'exécution : {e}", level="error")
        finally:
            # Re‑enable run button, disable cancel, clear feedback
            self.run_button.setEnabled(True)
            # self.cancel_button.setEnabled(False)
            self._feedback = None

    # ──────────────────────────────────────────────
    #  Process execution
    # ──────────────────────────────────────────────

    def _on_run(self):
        # Disable run, enable cancel
        self.run_button.setEnabled(False)
        # self.cancel_button.setEnabled(True)
        if self._selected_layer is None:
            return

        # Ensure the results group exists and is empty
        group = get_results_group(clear=True)

        layers = find_layers(exclude=self._selected_layer)
        if not layers:
            self._set_status("Aucune couche à comparer.", level="error")
            return

        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(lambda v: self.progress_bar.setValue(int(v)))  # type: ignore

        results = intersect_layer(
            self._selected_layer,
            layers,
            feedback=feedback,
        )

        if results:
            add_results_to_project(results)
            self._result_layers = results
            # PDF export requires basemap selection; keep disabled until basemap chosen
            self._set_export_enabled(csv=True, pdf=False)
            # Clean up the temporary "Objets créés" group if it exists
            objs_group = get_created_objects_group(clear=True)
            if objs_group:
                QgsProject.instance().layerTreeRoot().removeChildNode(objs_group)
            layer_count = max(len(results) - 1, 0)  # on enlève la couche source
            self._finish_progress(f"{layer_count} couches trouvées.")
        else:
            self._result_layers = []
            self._set_export_enabled(csv=False, pdf=False)
            self._finish_progress("Aucun résultat.")

    # ──────────────────────────────────────────────
    #  Export actions
    # ──────────────────────────────────────────────

    def _on_export_csv(self):
        # Verify that results group exists before exporting CSV
        if not self._verify_results_group():
            return
        folder = QFileDialog.getExistingDirectory(self, "Dossier CSV")
        if folder:
            export_results_to_csv(self._result_layers, folder)

    def _on_export_pdf(self):
        # Verify that results group exists before exporting PDF
        if not self._verify_results_group():
            return
        folder = QFileDialog.getExistingDirectory(self, "Dossier PDF")
        if folder:
            feedback = QgsProcessingFeedback()
            feedback.progressChanged.connect(lambda v: self.progress_bar.setValue(int(v)))  # type: ignore
            self._feedback = feedback
            # Disable run, enable cancel during export
            self.run_button.setEnabled(False)
            # self.cancel_button.setEnabled(True)
            try:
                export_results_to_pdf(
                    self._result_layers,
                    folder,
                    feedback=feedback,
                    basemap_layer=self._selected_basemap,
                )
            finally:
                # Restore UI state after export (whether success or error)
                self.run_button.setEnabled(True)
                # self.cancel_button.setEnabled(False)
                self._feedback = None

    def _verify_results_group(self):
        """Check if the 'Résultats secateur' group exists.

        If missing, update UI to show an error and disable export buttons.
        Returns True when the group is present, False otherwise.
        """
        # Use the DRY helper to locate the results group
        group = get_results_group()
        if not group:
            self._set_status("Aucun résultat Sécateur à exporter.", level="error")
            self._set_export_enabled(csv=False, pdf=False)
            return False
        return True

    # ──────────────────────────────────────────────
    #  Progress
    # ──────────────────────────────────────────────

    def _start_progress(self):
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

    def _update_progress(self, current, total, text):
        self.progress_bar.setValue(current)
        self._set_status(text, level="info")
        self._force_repaint()

    def _cancel_feedback(self):
        """Cancel the current processing feedback, if any."""
        if getattr(self, "_feedback", None):
            try:
                self._feedback.cancel()  # type: ignore
            except Exception:
                pass

    def _set_status(self, message: str, level: str = "info") -> None:
        """Update the status label and log the message.

        Parameters
        ----------
        message: str
            Text to display to the user.
        level: str, optional
            One of "info", "warning", "error". Determines visual cue and log level.
        """
        # Update UI label
        self.status_label.setText(message)
        # Simple colour hint – adjust stylesheet per level
        color_map = {
            "info": "",
            "warning": "color: orange;",
            "error": "color: red;",
        }
        style = color_map.get(level, "")
        if style:
            self.status_label.setStyleSheet(style)
        else:
            # Reset any previous style
            self.status_label.setStyleSheet("")
        # Log appropriately
        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
        else:
            pass

    def _finish_progress(self, text):
        self.progress_bar.setVisible(False)
        self._set_status(text, level="info")

    def _force_repaint(self):
        from qgis.PyQt.QtWidgets import QApplication

        QApplication.processEvents()
