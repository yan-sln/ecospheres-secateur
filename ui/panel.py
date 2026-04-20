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

from qgis.core import QgsProject, QgsVectorLayer

from ..core.export import export_results_to_csv, export_results_to_pdf
from ..core.intersector import find_layers, intersect_layer, add_results_to_project


class SecateurPanel(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Ecosphères Secateur", parent or iface.mainWindow())
        self.iface = iface

        self._layers = []
        self._selected_layer = None
        self._result_layers = []

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._do_search)

        self._build_ui()
        self._load_layers()

    # ---------------- UI ---------------- #

    def _build_ui(self):
        container = QWidget()
        layout = QVBoxLayout(container)

        layout.addWidget(QLabel("Couche source :"))

        self.layer_search = QLineEdit()
        self.layer_search.setPlaceholderText("Rechercher une couche…")
        self.layer_search.textChanged.connect(self._on_text_changed)

        self._model = QStringListModel()
        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.activated[str].connect(self._on_layer_selected)

        self.layer_search.setCompleter(self._completer)
        layout.addWidget(self.layer_search)

        self.active_btn = QPushButton("Utiliser la couche active")
        self.active_btn.clicked.connect(self._use_active_layer)
        layout.addWidget(self.active_btn)

        btn_row = QHBoxLayout()

        self.run_button = QPushButton("Interroger")
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self._on_run)
        btn_row.addWidget(self.run_button)

        self.export_csv_button = QPushButton("Exporter CSV")
        self.export_csv_button.setEnabled(False)
        self.export_csv_button.clicked.connect(self._on_export_csv)
        btn_row.addWidget(self.export_csv_button)

        self.export_pdf_button = QPushButton("Exporter PDF")
        self.export_pdf_button.setEnabled(False)
        self.export_pdf_button.clicked.connect(self._on_export_pdf)
        btn_row.addWidget(self.export_pdf_button)

        layout.addLayout(btn_row)

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
        self._layers = [l for l in QgsProject.instance().mapLayers().values() if isinstance(l, QgsVectorLayer)]
        self._model.setStringList(sorted([l.name() for l in self._layers]))

    def _on_text_changed(self, text):
        self._selected_layer = None
        self.run_button.setEnabled(False)

        if len(text) >= 1:
            self._debounce_timer.start()

    def _do_search(self):
        text = self.layer_search.text().lower()
        filtered = [l.name() for l in self._layers if text in l.name().lower()]
        self._model.setStringList(sorted(filtered))

    def _on_layer_selected(self, text):
        for layer in self._layers:
            if layer.name() == text:
                self._selected_layer = layer
                self.status_label.setText(f"Couche sélectionnée : {layer.name()}")
                self.run_button.setEnabled(True)
                return

    def _use_active_layer(self):
        layer = self.iface.activeLayer()
        if isinstance(layer, QgsVectorLayer):
            self._selected_layer = layer
            # Bloquer temporairement les signaux du champ de recherche pour éviter que
            # setText déclenche _on_text_changed, qui réinitialiserait la sélection.
            self.layer_search.blockSignals(True)
            self.layer_search.setText(layer.name())
            self.layer_search.blockSignals(False)
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
            self.export_pdf_button.setEnabled(True)

            total = sum(r.featureCount() for r in results)
            self._finish_progress(f"{total} entités trouvées.")
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
            # export_results_to_pdf(self._result_layers, "Résultats", None, folder)
            pass

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
