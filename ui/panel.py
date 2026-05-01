from contextlib import suppress
from dataclasses import dataclass, field

from qgis.core import QgsFeature, QgsMapLayerProxyModel, QgsProcessingFeedback, QgsVectorLayer
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.export import export_results_to_csv, export_results_to_pdf
from ..core.logger import logger
from ..core.utils import get_results_group
from .service import SecateurService
from .settings import SettingsManager

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

    def __post_init__(self):
        assert isinstance(self.result_layers, list)


class SecateurPanel(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Ecosphères Secateur", parent or iface.mainWindow())
        self.iface = iface

        self.settings = SettingsManager()
        self.state = _SecateurState()
        self.service = SecateurService()

        self._selected_basemap = None
        self._feedback: QgsProcessingFeedback | None = None

        self._build_ui()

    # UI construction identical (unchanged)
    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)

        layout.addWidget(QLabel("Sélectionner l'objet à intersecter :"))

        btn_row = QHBoxLayout()
        self.run_button = QPushButton("Utiliser la géométrie active")
        self.run_button.clicked.connect(self._execute)
        btn_row.addWidget(self.run_button)
        layout.addLayout(btn_row)

        self.export_csv_button = QPushButton("Exporter CSV")
        self.export_csv_button.setEnabled(False)
        self.export_csv_button.clicked.connect(self._on_export_csv)
        layout.addWidget(self.export_csv_button)

        layout.addWidget(QLabel("Fond de carte :"))

        self.basemap_combo = QgsMapLayerComboBox()
        self.basemap_combo.setFilters(QgsMapLayerProxyModel.RasterLayer)  # type: ignore
        self.basemap_combo.layerChanged.connect(self._on_basemap_selected)  # type: ignore
        layout.addWidget(self.basemap_combo)

        raster_layers = self.service.get_available_raster_layers()
        if raster_layers:
            default_basemap = raster_layers[0]
            self.basemap_combo.setLayer(default_basemap)
            self._selected_basemap = default_basemap

        layout.addWidget(QLabel("Titre du GeoPDF :"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Titre du rapport")
        self.title_input.setText(self.settings.pdf_title)
        layout.addWidget(self.title_input)

        geopdf_row = QHBoxLayout()

        self.export_pdf_button = QPushButton("Exporter PDF")
        self.export_pdf_button.setEnabled(False)
        self.export_pdf_button.clicked.connect(self._on_export_pdf)
        geopdf_row.addWidget(self.export_pdf_button)

        self.edit_author_button = QPushButton("Modifier l’auteur…")
        self.edit_author_button.clicked.connect(self._on_edit_author)
        geopdf_row.addWidget(self.edit_author_button)

        layout.addLayout(geopdf_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setWidget(container)

    # UI helpers (unchanged)
    def _set_export_enabled(self, csv=None, pdf=None):
        if csv is not None:
            self.export_csv_button.setEnabled(csv)
        if pdf is not None:
            self.export_pdf_button.setEnabled(pdf)

    def _set_status(self, message, level="info"):
        if message:
            self.status_label.setText(message)

        color_map = {"info": "", "warning": "color: orange;", "error": "color: red;"}
        self.status_label.setStyleSheet(color_map.get(level, "") or "")

        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)

    def _on_basemap_selected(self, layer):
        if layer is None:
            self._selected_basemap = None
            self._set_status("Fond de carte non sélectionné.", "warning")
            return

        self._selected_basemap = layer
        self._set_status(f"Fond de carte sélectionné : {layer.name()}", "info")

    def _on_edit_author(self):
        current = self.settings.author
        text, ok = QInputDialog.getText(
            self,
            "Modifier l’auteur",
            "Nom de l’auteur :",
            text=current,
        )
        if not ok or not text.strip():
            return
        #!!! Ici ajouter tests sur chaîne (longueur, etc.)
        try:
            self.settings.author = text
            self._set_status(f"Auteur mis à jour : {text}", "info")
        except ValueError as e:
            self._set_status(str(e), "error")

    # ──────────────────────────────────────────────
    #  Execution (rewired)
    # ──────────────────────────────────────────────

    def _execute(self):
        selection = self.service.select(self.iface)

        if selection.message:
            self._set_status(selection.message, selection.level)

        if selection.layer is None:
            return

        self.state.selected_layer = selection.layer
        self.state.selected_feature = selection.feature

        try:
            result = self._run_process()
            self._set_export_enabled(pdf=True)
            if result.level != "error" and self._selected_basemap is None:
                self._set_status("Fond de carte non sélectionné.", "warning")
        except Exception as e:
            self._set_status(f"Erreur d'exécution : {e}", "error")
        finally:
            self.run_button.setEnabled(True)
            self._feedback = None

    def _run_process(self):
        assert self.state.selected_layer is not None

        self.run_button.setEnabled(False)

        feedback = self._create_feedback()

        result = self.service.run(self.state.selected_layer, feedback)

        self.state.result_layers = result.result_layers

        self._set_status(result.message, result.level)

        if result.result_layers:
            self._set_export_enabled(csv=True, pdf=False)
        else:
            self._set_export_enabled(csv=False, pdf=False)

        self._finish_progress(result.message)
        return result

    # Export unchanged
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

            title = self.title_input.text().strip()
            if not title:
                self._set_status("Le titre ne peut pas être vide.", "error")
                return

            try:
                full_path = export_results_to_pdf(
                    self.state.result_layers,
                    folder,
                    feedback=feedback,
                    basemap_layer=self._selected_basemap,
                    author=self.settings.author,
                    title=title,
                )
                self.settings.pdf_title = title
                self._set_status(f"GeoPDF exporté : {full_path}", "info")
            finally:
                self.run_button.setEnabled(True)
                self._feedback = None

    def _verify_results_group(self):
        group = get_results_group()
        if not group:
            self._set_status("Aucun résultat à exporter.", "error")
            self._set_export_enabled(csv=False, pdf=False)
            return False
        return True

    # Progress unchanged
    def _create_feedback(self):
        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(lambda v: self.progress_bar.setValue(int(v)))  # type: ignore
        return feedback

    def _finish_progress(self, text):
        self.progress_bar.setVisible(False)
        self._set_status(text, "info")

    def _cancel_feedback(self):
        if self._feedback:
            with suppress(Exception):
                self._feedback.cancel()

    def _force_repaint(self):
        from qgis.PyQt.QtWidgets import QApplication

        QApplication.processEvents()
