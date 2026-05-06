from contextlib import suppress
from dataclasses import dataclass, field

from qgis.core import QgsApplication, QgsFeature, QgsMapLayerProxyModel, QgsProcessingFeedback, QgsTask, QgsVectorLayer
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtWidgets import (
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

from ..core.export import _export_csv_task, _export_pdf_task
from ..core.image_manager import ImageManager
from ..core.logger import logger
from ..core.utils import get_results_group
from .service import SecateurService
from .settings import SettingsDialog, SettingsManager

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
        self.image_manager = ImageManager()
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
            self._selected_basemap = default_basemap

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
        has_results = bool(self.state.result_layers)

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

    def _on_basemap_selected(self, layer):
        if layer is None:
            self._selected_basemap = None
            self._set_status("Fond de carte non sélectionné.", "warning")
            return

        self._selected_basemap = layer
        self._set_status(f"Fond de carte sélectionné : {layer.name()}", "info")

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

    # ---------------------------------------------------------------------
    #  Task helpers – run export functions in a QgsTask
    # ---------------------------------------------------------------------
    def _run_task(self, name: str, fn, *args, **kwargs):
        """Create and start a QgsTask that executes *fn* with a feedback object.
        ``fn`` must accept a ``feedback`` keyword argument (the task will pass the
        same QgsProcessingFeedback instance that is stored in ``self._feedback``).
        The task reports progress via the QGIS task manager and invokes
        ``self._task_finished`` when done or cancelled.
        """

        # Fresh feedback for each task
        # Create a fresh feedback object via the task itself.
        # The task will own the QgsProcessingFeedback instance; we keep a
        # reference so the cancel button can call ``cancel()``.
        def task_func(task: QgsTask, fb: QgsProcessingFeedback):
            # Forward the feedback to the wrapped export function.
            try:
                result = fn(*args, feedback=fb, **kwargs)

                return result
            except Exception as e:
                # Log the exception to help debugging
                logger.exception(f"Task {name} failed with exception: {e}")
                # Re-raise the exception so the QgsTask system knows about it
                raise

        try:
            task = QgsTask.fromFunction(
                name,
                task_func,
                on_finished=lambda task, exception, result=None: self._task_finished(exception is None, result),
            )

            # Register with QGIS UI
            QgsApplication.taskManager().addTask(task)

            # UI feedback while running
            self.run_button.setEnabled(False)
            self.export_pdf_button.setEnabled(False)
            self.export_csv_button.setEnabled(False)
            self._set_status(f"{name} en cours…", "info")
        except Exception as e:
            logger.exception(f"Failed to start task {name}: {e}")
            self._set_status(f"Échec du démarrage de la tâche {name}: {e}", "error")
            self.run_button.setEnabled(True)
            self.export_pdf_button.setEnabled(bool(self.state.result_layers))
            self.export_csv_button.setEnabled(bool(self.state.result_layers))

    def _task_finished(self, success: bool, result):
        """Handle completion of a background task.
        *success* indicates the task finished without cancellation. *result* is
        whatever the wrapped export function returned.
        """
        # Reset UI state
        self.run_button.setEnabled(True)
        self.export_pdf_button.setEnabled(bool(self.state.result_layers))
        self.export_csv_button.setEnabled(bool(self.state.result_layers))
        self._feedback = None

        if not success:
            self._set_status("Export annulé par l'utilisateur.", "warning")
            return

        # Differentiate CSV (list) vs PDF (tuple) results
        if isinstance(result, list):
            self._set_status(f"{len(result)} CSV exporté(s).", "info")
        elif isinstance(result, tuple) and len(result) == 2:
            full_path, _ = result
            self.settings.pdf_title = self.title_input.text().strip()
            self._set_status(f"GeoPDF exporté : {full_path}", "info")
        elif result is None:
            # Handle case where result is None (likely an error occurred)
            self._set_status("Erreur lors de l'export du GeoPDF.", "error")
        else:
            self._set_status("Export terminé (résultat inconnu).", "info")

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
            if result.level != "error" and self._selected_basemap is None:
                self._set_status("Fond de carte non sélectionné.", "warning")
        except Exception as e:
            self._set_status(f"Erreur d'exécution : {e}", "error")
        finally:
            self.run_button.setEnabled(True)
            self._feedback = None

    def _run_process(self):
        assert self.state.selected_layer is not None

        feedback = self._create_feedback()

        result = self.service.run(self.state.selected_layer, feedback)

        self.state.result_layers = result.result_layers

        self._set_status(result.message, result.level)

        self._update_ui_state()

        self._finish_progress(result.message)
        return result

    def _on_export_csv(self):
        if not self._verify_results_group():
            return

        folder = QFileDialog.getExistingDirectory(self, "Dossier CSV")
        if not folder:
            return

        # Direct export (bypass background task)
        self._set_status("Export CSV en cours...", "info")
        try:
            result = _export_csv_task(self.state.result_layers, folder, feedback=None)
            self._set_status(f"{len(result)} CSV exporté(s).", "info")
        except Exception as e:
            logger.exception(f"CSV export failed: {e}")
            self._set_status(f"Erreur lors de l'export CSV: {e}", "error")

    def _on_export_pdf(self):
        if not self._verify_results_group():
            return

        folder = QFileDialog.getExistingDirectory(self, "Dossier PDF")
        if not folder:
            return

        title = self.title_input.text().strip()
        if not title:
            self._set_status("Le titre ne peut pas être vide.", "error")
            return

        # Direct export (bypass background task)
        self._set_status("Export GeoPDF en cours...", "info")

        try:
            result = _export_pdf_task(
                self.state.result_layers,
                folder,
                self.settings.logo_path,
                feedback=None,
                basemap_layer=self._selected_basemap,
                author=self.settings.author,
                title=title,
            )
            # Process the result similarly to _task_finished
            full_path, _ = result
            self.settings.pdf_title = title
            self._set_status(f"GeoPDF exporté : {full_path}", "info")
        except Exception as e:
            logger.exception(f"Direct PDF export failed: {e}")
            self._set_status(f"Erreur lors de l'export du GeoPDF: {e}", "error")

    def _verify_results_group(self):
        group = get_results_group()
        if not group:
            self._set_status("Aucun résultat à exporter.", "error")
            self._update_ui_state()
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

    def _force_repaint(self):
        from qgis.PyQt.QtWidgets import QApplication

        QApplication.processEvents()
