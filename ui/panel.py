from qgis.gui import QgsMapLayerComboBox
from qgis.core import QgsProject, QgsVectorLayer, QgsMapLayer, QgsMapLayerProxyModel
from qgis.PyQt.QtCore import QStringListModel, Qt, QTimer
from qgis.PyQt.QtWidgets import (
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

from ..core.export import export_results_to_csv, export_results_to_pdf
from ..core.intersector import add_results_to_project, find_layers, intersect_layer


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

    # ---------------- UI ---------------- #

    def _build_ui(self):
        # Build the UI with source layer selector, run button, CSV export, basemap selector, and PDF export
        container = QWidget()
        layout = QVBoxLayout(container)

        #
        layout.addWidget(QLabel("Couche source :"))

        self.layer_combo = QgsMapLayerComboBox()
        self.layer_combo.setFilters(QgsMapLayerProxyModel.VectorLayer)  # type: ignore
        self.layer_combo.layerChanged.connect(self._on_layer_selected)  # type: ignore

        layout.addWidget(self.layer_combo)

        #
        self.active_btn = QPushButton("Utiliser la couche active")
        self.active_btn.clicked.connect(self._use_active_layer)
        layout.addWidget(self.active_btn)

        # Row with Interroger button only
        btn_row = QHBoxLayout()
        self.run_button = QPushButton("Interroger")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._on_run)
        btn_row.addWidget(self.run_button)
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
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setWidget(container)

    # ---------------- LAYERS ---------------- #

    def _load_layers(self):
        # Load vector layers for source selection
        self._layers = [l for l in QgsProject.instance().mapLayers().values() if isinstance(l, QgsVectorLayer)]
        # Load all layers (vector + raster) for basemap selection
        self._all_layers = list(QgsProject.instance().mapLayers().values())

    def _on_layer_selected(self, layer):
        if layer is None:
            self._selected_layer = None
            self.run_button.setEnabled(False)
            self.status_label.setText("Aucune couche sélectionnée.")
            return

        self._selected_layer = layer
        self.status_label.setText(f"Couche sélectionnée : {layer.name()}")
        self.run_button.setEnabled(True)

    def _on_basemap_selected(self, layer):
        if layer is None:
            self._selected_basemap = None
            self.status_label.setText("Fond de carte non sélectionné.")
            self.export_pdf_button.setEnabled(False)
            return

        self._selected_basemap = layer
        self.status_label.setText(f"Fond de carte sélectionné : {layer.name()}")
        self.export_pdf_button.setEnabled(True)

    def _use_active_layer(self):
        layer = self.iface.activeLayer()
        if isinstance(layer, QgsVectorLayer):
            self._selected_layer = layer
            self.status_label.setText(f"Couche active : {layer.name()}")
            self.run_button.setEnabled(True)
        else:
            self.status_label.setText("Aucune couche vectorielle active.")

    # ---------------- PROCESS ---------------- #

    def _on_run(self):
        if self._selected_layer is None:
            return

        layers = find_layers(exclude=self._selected_layer)

        if not layers:
            self.status_label.setText("Aucune couche à comparer.")
            return

        self._start_progress(len(layers))

        def progress(current, total, name):
            self._update_progress(current, total, f"{current + 1}/{total} : {name}")

        results = intersect_layer(
            self._selected_layer,
            layers,
            progress_callback=progress,
        )

        if results:
            add_results_to_project(results)
            self._result_layers = results

            self.export_csv_button.setEnabled(True)
            # PDF export requires basemap selection; keep disabled until basemap chosen
            self.export_pdf_button.setEnabled(False)

            layer_count = len(results)
            self._finish_progress(f"{layer_count} couches trouvées.")
        else:
            self._result_layers = []
            self.export_csv_button.setEnabled(False)
            self.export_pdf_button.setEnabled(False)
            self._finish_progress("Aucun résultat.")

    # ---------------- EXPORT ---------------- #

    def _on_export_csv(self):
        folder = QFileDialog.getExistingDirectory(self, "Dossier CSV")
        if folder:
            export_results_to_csv(self._result_layers, folder)

    def _on_export_pdf(self):
        folder = QFileDialog.getExistingDirectory(self, "Dossier PDF")
        if folder:
            export_results_to_pdf(
                self._result_layers,
                folder,
                progress_callback=self._update_progress,
                basemap_layer=self._selected_basemap,
            )

    # ---------------- PROGRESS ---------------- #

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
        from qgis.PyQt.QtWidgets import QApplication

        QApplication.processEvents()
