from contextlib import contextmanager, suppress
from dataclasses import dataclass, field

from qgis.core import QgsMapLayerProxyModel, QgsProcessingFeedback, QgsVectorLayer
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.export import export_results_to_csv, export_results_to_pdf
from ..core.image_manager import ImageManager
from ..core.layer_resolver import LayerResolver
from ..core.logger import logger
from .service import ProcessResult, SecateurService
from .settings import SettingsDialog, SettingsManager


@contextmanager
def wait_cursor():
    """Push a waiting cursor and guarantee its restoration.

    Uses Qt's override‑cursor stack; the cursor is restored even if the
    surrounding block raises or returns early.
    """
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()


# ──────────────────────────────────────────────
#  State object with explicit invariants
# ──────────────────────────────────────────────


@dataclass
class _SecateurState:
    # Invariant:
    # - None before valid selection
    # - layer ID after _handle_selection if success
    selected_layer_id: str | None = None

    # Invariant:
    # - always a list (never None)
    # - contains only layer IDs
    result_layer_ids: list[str] = field(default_factory=list)

    def __post_init__(self):
        assert isinstance(self.result_layer_ids, list)


class SecateurPanel(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Ecosphères Secateur", parent or iface.mainWindow())
        self.iface = iface

        self.settings = SettingsManager()
        self.image_manager = ImageManager()
        self.state = _SecateurState()
        self.service = SecateurService()

        self._selected_basemap_id: str | None = None
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

        geopdf_frame = QFrame()
        geopdf_frame.setFrameShape(QFrame.StyledPanel)
        geopdf_layout = QVBoxLayout(geopdf_frame)

        geopdf_title_label = QLabel("Export GeoPDF")
        geopdf_title_label.setStyleSheet("font-weight: bold;")
        geopdf_layout.addWidget(geopdf_title_label)

        geopdf_layout.addWidget(QLabel("Choisir un fond de carte :"))

        self.basemap_combo = QgsMapLayerComboBox()
        self.basemap_combo.setFilters(QgsMapLayerProxyModel.RasterLayer)  # type: ignore
        self.basemap_combo.layerChanged.connect(self._on_basemap_selected)  # type: ignore
        geopdf_layout.addWidget(self.basemap_combo)

        raster_layers = self.service.get_available_raster_layers()
        if raster_layers:
            default_basemap = raster_layers[0]
            self.basemap_combo.setLayer(default_basemap)
            self._selected_basemap_id = default_basemap.id()

        geopdf_layout.addWidget(QLabel("Modifier le titre :"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Titre du GeoPDF")
        self.title_input.setText(self.settings.pdf_title)
        geopdf_layout.addWidget(self.title_input)

        geopdf_row = QHBoxLayout()

        self.export_pdf_button = QPushButton("Exporter le GeoPDF")
        self.export_pdf_button.clicked.connect(self._on_export_pdf)
        geopdf_row.addWidget(self.export_pdf_button)

        self.edit_settings_button = QPushButton("Paramètres…")
        self.edit_settings_button.clicked.connect(self._open_settings_dialog)
        geopdf_row.addWidget(self.edit_settings_button)

        geopdf_layout.addLayout(geopdf_row)

        layout.addWidget(geopdf_frame)
        geopdf_frame.setEnabled(False)

        # ~~~~~~~~~~~~~~~ csv frame ~~~~~~~~~~~~~~~#
        csv_frame = QFrame()
        csv_frame.setFrameShape(QFrame.StyledPanel)
        csv_layout = QVBoxLayout(csv_frame)

        csv_title_label = QLabel("Export CSV")
        csv_title_label.setStyleSheet("font-weight: bold;")
        csv_layout.addWidget(csv_title_label)

        csv_layout.addWidget(QLabel("Exporter les tables de vérités :"))

        self.export_csv_button = QPushButton("Export CSV")
        self.export_csv_button.clicked.connect(self._on_export_csv)
        csv_layout.addWidget(self.export_csv_button)

        layout.addWidget(csv_frame)
        csv_frame.setEnabled(False)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setWidget(container)

        self.csv_frame = csv_frame
        self.geopdf_frame = geopdf_frame

        self._update_ui_state()

    def _update_ui_state(self):
        has_results = bool(self._resolve_result_layers())

        self.csv_frame.setEnabled(has_results)
        self.geopdf_frame.setEnabled(has_results)

    def _set_status(self, message, level="info"):
        if message:
            self.status_label.setText(message)

        color_map = {"info": "", "warning": "color: orange;", "error": "color: red;"}
        self.status_label.setStyleSheet(color_map.get(level, "") or "")

        if level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)

    def _resolve_selected_layer(self) -> QgsVectorLayer | None:
        if not self.state.selected_layer_id:
            return None

        return LayerResolver.get_vector(self.state.selected_layer_id)

    def _resolve_result_layers(self):
        return LayerResolver.get_many(self.state.result_layer_ids)

    def _resolve_basemap(self):
        if not self._selected_basemap_id:
            return None

        return LayerResolver.get(self._selected_basemap_id)

    def _open_settings_dialog(self):
        dlg = SettingsDialog(self.settings, self.image_manager, self)

        try:
            if not dlg.exec_():
                return

            values = dlg.get_values()

            author = values["author"]
            if not author:
                self._set_status("Auteur invalide.", "error")
                return

            logo_path = self.settings.logo_path  # fallback

            if values["logo"]:
                logo_path = self.image_manager.safe_import_logo(values["logo"])

            self.settings.author = author
            self.settings.logo_path = logo_path

            self._set_status("Paramètres mis à jour.", "info")

        except ValueError as e:
            # erreurs métier (validation image)
            self._set_status(str(e), "error")

        except Exception as e:
            # erreurs inattendues (IO, filesystem, etc.)
            self._set_status(f"Erreur inattendue : {e}", "error")

    def _on_basemap_selected(self, layer):
        if layer is None:
            self._selected_basemap_id = None
            self._set_status("Fond de carte non sélectionné.", "warning")
            return

        self._selected_basemap_id = layer.id()
        self._set_status(f"Fond de carte sélectionné : {layer.name()}", "info")

    # ──────────────────────────────────────────────
    #  Execution
    # ──────────────────────────────────────────────

    def _execute(self):
        # Use a context manager to guarantee cursor restoration
        # even if an exception occurs or the function returns early.

        selection = self.service.select(self.iface)

        if selection.message:
            self._set_status(selection.message, selection.level)

        if selection.layer is None:
            return

        self.state.selected_layer_id = selection.layer.id() if selection.layer else None

        try:
            with wait_cursor():
                result = self._run_process()
                if result.level != "error" and self._selected_basemap_id is None:
                    self._set_status("Fond de carte non sélectionné.", "warning")
        except Exception as e:
            self._set_status(f"Erreur d'exécution : {e}", "error")
        finally:
            self.run_button.setEnabled(True)
            self._feedback = None

    def _run_process(self):
        selected_layer = self._resolve_selected_layer()

        if selected_layer is None:
            self._set_status(
                "La couche sélectionnée n'existe plus.",
                "error",
            )

            return ProcessResult(
                [],
                "La couche sélectionnée n'existe plus.",
                "error",
            )

        feedback = self._create_feedback()

        result = self.service.run(
            selected_layer.id(),
            feedback,
        )

        self.state.result_layer_ids = result.result_layer_ids

        self._set_status(result.message, result.level)

        self._update_ui_state()

        self._finish_progress(result.message)
        return result

    def _on_export_csv(self):
        if not self._verify_results_exist():
            return

        folder = QFileDialog.getExistingDirectory(self, "Dossier CSV")
        if not folder:
            return

        self._begin_busy_ui("Export CSV en cours...")

        QTimer.singleShot(
            0,
            lambda: self._execute_csv_export(folder),
        )

    def _execute_csv_export(self, folder: str):
        feedback = self._create_feedback()

        try:
            with wait_cursor():
                result = export_results_to_csv(
                    self._resolve_result_layers(),
                    folder,
                    feedback=feedback,
                )

                self._set_status(
                    f"{len(result)} CSV exporté(s).",
                    "info",
                )

        except Exception as e:
            logger.exception(f"CSV export failed: {e}")

            self._set_status(
                f"Erreur lors de l'export CSV: {e}",
                "error",
            )

        finally:
            self._end_busy_ui()

    def _on_export_pdf(self):
        if not self._verify_results_exist():
            return

        folder = QFileDialog.getExistingDirectory(self, "Dossier PDF")
        if not folder:
            return

        title = self.title_input.text().strip()

        if not title:
            self._set_status("Le titre ne peut pas être vide.", "error")
            return

        self._begin_busy_ui("Export GeoPDF en cours...")

        QTimer.singleShot(
            0,
            lambda: self._execute_pdf_export(folder, title),
        )

    def _execute_pdf_export(self, folder: str, title: str):
        feedback = self._create_feedback()

        try:
            with wait_cursor():
                result = export_results_to_pdf(
                    self._resolve_result_layers(),
                    folder,
                    self.settings.logo_path,
                    feedback=feedback,
                    basemap_layer=self._resolve_basemap(),
                    author=self.settings.author,
                    title=title,
                )

                self.settings.pdf_title = title

                self._set_status(
                    f"GeoPDF exporté : {result}",
                    "info",
                )

        except Exception as e:
            logger.exception(f"Direct PDF export failed: {e}")

            self._set_status(
                f"Erreur lors de l'export du GeoPDF: {e}",
                "error",
            )

        finally:
            self._end_busy_ui()

    def _invalidate_results(self):
        self.state.result_layer_ids = []

        self._update_ui_state()

        self._set_status(
            ("Les couches de résultat ont été supprimées du projet. Relancez le traitement."),
            "warning",
        )

    def _verify_results_exist(self):
        layers = self._resolve_result_layers()

        if not layers:
            self._invalidate_results()
            return False

        return True

    # Progress unchanged
    def _create_feedback(self):
        return QgsProcessingFeedback()

    def _finish_progress(self, text):
        self._set_status(text, "info")

    def _cancel_feedback(self):
        if self._feedback:
            with suppress(Exception):
                self._feedback.cancel()

    def _begin_busy_ui(self, message: str):
        self.run_button.setEnabled(False)
        self.export_pdf_button.setEnabled(False)
        self.export_csv_button.setEnabled(False)

        self._set_status(message, "info")

    def _end_busy_ui(self):
        self.run_button.setEnabled(True)
        self.export_pdf_button.setEnabled(bool(self._resolve_result_layers()))
        self.export_csv_button.setEnabled(bool(self._resolve_result_layers()))

        self._feedback = None
