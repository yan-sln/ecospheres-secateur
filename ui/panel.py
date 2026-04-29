from contextlib import suppress
from dataclasses import dataclass, field

from qgis.core import QgsFeature, QgsMapLayerProxyModel, QgsProcessingFeedback, QgsProject, QgsVectorLayer, QgsWkbTypes
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

from ..core.constants import CREATED_OBJECTS_GROUP_NAME, RESULT_GROUP_NAME
from ..core.export import export_results_to_csv, export_results_to_pdf
from ..core.intersector import add_results_to_project, intersect_layer
from ..core.logger import logger
from ..core.utils import find_layers, get_created_objects_group, get_results_group

# ──────────────────────────────────────────────
#  State object with explicit invariants
# ──────────────────────────────────────────────


@dataclass
class _SecateurState:
    # Invariant:
    # - None before valid selection
    # - QgsVectorLayer after _handle_selection if success
    selected_layer: QgsVectorLayer | None = None

    # None means:
    # - no feature selected
    # - OR multiple features selected
    selected_feature: QgsFeature | None = None

    # Invariant:
    # - always a list (never None)
    # - contains only QgsVectorLayer
    result_layers: list[QgsVectorLayer] = field(default_factory=list)


class SecateurPanel(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Ecosphères Secateur", parent or iface.mainWindow())
        self.iface = iface

        self.state = _SecateurState()

        # Instance state (avoid class-level shared state)
        self._selected_basemap = None
        self._feedback: QgsProcessingFeedback | None = None

        self._build_ui()

    # ──────────────────────────────────────────────
    #  UI construction
    # ──────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)

        layout.addWidget(QLabel("Sélectionner l'objet à intersecter :"))

        btn_row = QHBoxLayout()
        self.run_button = QPushButton("Utiliser la géométrie active")
        self.run_button.clicked.connect(self._execute)
        btn_row.addWidget(self.run_button)
        layout.addLayout(btn_row)

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
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setWidget(container)

    # ──────────────────────────────────────────────
    #  UI helpers
    # ──────────────────────────────────────────────

    def _set_export_enabled(self, csv: bool | None = None, pdf: bool | None = None) -> None:
        if csv is not None:
            self.export_csv_button.setEnabled(csv)
        if pdf is not None:
            self.export_pdf_button.setEnabled(pdf)

    def _set_status(self, message: str, level: str = "info") -> None:
        self.status_label.setText(message)

        color_map = {
            "info": "",
            "warning": "color: orange;",
            "error": "color: red;",
        }
        self.status_label.setStyleSheet(color_map.get(level, "") or "")

        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)

    # ──────────────────────────────────────────────
    #  Basemap
    # ──────────────────────────────────────────────

    def _on_basemap_selected(self, layer):
        if layer is None:
            self._selected_basemap = None
            self._set_status("Fond de carte non sélectionné.", level="warning")
            self._set_export_enabled(pdf=False)
            return

        self._selected_basemap = layer
        self._set_status(f"Fond de carte sélectionné : {layer.name()}", level="info")
        self._set_export_enabled(pdf=True)

    # ──────────────────────────────────────────────
    #  Selection logic
    # ──────────────────────────────────────────────

    def _prepare_source_layer(self) -> QgsVectorLayer | None:
        self.state.selected_layer = None
        self.state.selected_feature = None

        layer = self.iface.activeLayer()

        if layer is None:
            self._set_status("Aucune entité active.", level="warning")
            return None

        if not isinstance(layer, QgsVectorLayer):
            self._set_status("Sélection réinitialisée (pas de couche vectorielle).", level="warning")
            return None

        results_group = get_results_group()
        if results_group is None:
            self._set_status("Impossible d'accéder au groupe 'Résultats secateur'.", level="error")
            return None

        if results_group.findLayer(layer.id()) is not None:
            self._set_status(f"La sélection appartient au groupe {RESULT_GROUP_NAME}.", level="warning")
            return None

        return layer

    def _handle_selection(self):
        layer = self._prepare_source_layer()
        if layer is None:
            return

        selected = layer.selectedFeatures()

        if len(selected) == 1:
            self._handle_single_feature(layer, selected[0])
        elif len(selected) > 1:
            self._handle_multiple_features(layer)
        else:
            self._handle_no_selection(layer)

        # Contract: after this, selected_layer must be set
        assert self.state.selected_layer is not None

    def _handle_single_feature(self, layer, feature):
        mem_layer = self._create_memory_layer_from_feature(layer, feature)

        group = get_created_objects_group()
        if group is None:
            self._set_status(
                f"Impossible d'ajouter la couche : groupe '{CREATED_OBJECTS_GROUP_NAME}' introuvable.",
                level="error",
            )
        else:
            group.insertLayer(-1, mem_layer)

        self.state.selected_layer = mem_layer
        self.state.selected_feature = feature

    def _handle_multiple_features(self, layer):
        self.state.selected_layer = layer
        self.state.selected_feature = None
        self._set_status("Plusieurs objets sélectionnés !", level="warning")

    def _handle_no_selection(self, layer):
        self.state.selected_layer = layer
        self.state.selected_feature = None
        self._set_status(f"Couche sélectionnée : {layer.name()}", level="info")

    def _create_memory_layer_from_feature(self, source_layer, feature):
        layer_name = f"{source_layer.name()}_feature_{feature.id()}"
        project = QgsProject.instance()

        for lyr in project.mapLayersByName(layer_name):
            project.removeMapLayer(lyr)

        geom_type = QgsWkbTypes.displayString(source_layer.wkbType())
        mem_layer = QgsVectorLayer(
            f"{geom_type}?crs={source_layer.crs().authid()}",
            layer_name,
            "memory",
        )

        mem_layer.dataProvider().addAttributes(source_layer.fields())
        mem_layer.updateFields()

        new_feat = QgsFeature()
        new_feat.setGeometry(feature.geometry())
        new_feat.setAttributes(feature.attributes())
        mem_layer.dataProvider().addFeature(new_feat)
        mem_layer.updateExtents()

        project.addMapLayer(mem_layer, False)
        return mem_layer

    # ──────────────────────────────────────────────
    #  Execution
    # ──────────────────────────────────────────────

    def _execute(self):
        self._handle_selection()
        if self.state.selected_layer is None:
            return

        try:
            self._run_process()
        except Exception as e:
            self._set_status(f"Erreur d'exécution : {e}", level="error")
        finally:
            self.run_button.setEnabled(True)
            self._feedback = None

    def _run_process(self):
        # Contract: must have a selected layer
        assert self.state.selected_layer is not None

        self.run_button.setEnabled(False)

        group = get_results_group(clear=True)
        if group is None:
            self._set_status("Impossible d'accéder au groupe 'Résultats secateur'.", level="error")
            self.run_button.setEnabled(True)
            return

        layers = find_layers(exclude=self.state.selected_layer)
        if not layers:
            self._set_status("Aucune couche visible à comparer.", level="error")
            return

        feedback = self._create_feedback()

        results = intersect_layer(
            self.state.selected_layer,
            layers,
            feedback=feedback,
        )

        self._handle_results(results)

    def _handle_results(self, results):
        if results:
            add_results_to_project(results)
            self.state.result_layers = results

            self._set_export_enabled(csv=True, pdf=False)

            objs_group = get_created_objects_group(clear=True)
            if objs_group is None:
                self._set_status(
                    f"Groupe '{CREATED_OBJECTS_GROUP_NAME}' introuvable lors du nettoyage.",
                    level="warning",
                )
            else:
                QgsProject.instance().layerTreeRoot().removeChildNode(objs_group)

            layer_count = max(len(results) - 1, 0)
            self._finish_progress(f"{layer_count} couches trouvées.")
        else:
            self.state.result_layers = []
            self._set_export_enabled(csv=False, pdf=False)
            self._finish_progress("Aucun résultat.")

        # Contract: result_layers always a list
        assert isinstance(self.state.result_layers, list)

    # ──────────────────────────────────────────────
    #  Export
    # ──────────────────────────────────────────────

    def _on_export_csv(self):
        if not self._verify_results_group():
            return

        folder = QFileDialog.getExistingDirectory(self, "Dossier CSV")
        if folder:
            export_results_to_csv(self.state.result_layers, folder)

    def _on_export_pdf(self):
        if not self._verify_results_group():
            return

        folder = QFileDialog.getExistingDirectory(self, "Dossier PDF")
        if folder:
            feedback = self._create_feedback()
            self._feedback = feedback

            self.run_button.setEnabled(False)

            try:
                export_results_to_pdf(
                    self.state.result_layers,
                    folder,
                    feedback=feedback,
                    basemap_layer=self._selected_basemap,
                )
            finally:
                self.run_button.setEnabled(True)
                self._feedback = None

    def _verify_results_group(self):
        group = get_results_group()
        if not group:
            self._set_status("Aucun résultat à exporter.", level="error")
            self._set_export_enabled(csv=False, pdf=False)
            return False
        return True

    # ──────────────────────────────────────────────
    #  Progress
    # ──────────────────────────────────────────────

    def _create_feedback(self):
        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(lambda v: self.progress_bar.setValue(int(v)))  # type: ignore
        return feedback

    def _finish_progress(self, text):
        self.progress_bar.setVisible(False)
        self._set_status(text, level="info")

    def _cancel_feedback(self):
        if self._feedback:
            with suppress(Exception):
                self._feedback.cancel()

    def _force_repaint(self):
        from qgis.PyQt.QtWidgets import QApplication

        QApplication.processEvents()
