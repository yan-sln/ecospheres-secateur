from PyQt5.QtCore import QStringListModel, Qt, QTimer
from PyQt5.QtWidgets import (
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

from ..core.commune_api import fetch_commune_geometry, search_communes
from ..core.export import export_results_to_csv, export_results_to_pdf
from ..core.intersector import add_results_to_project, find_wfs_layers, intersect_commune


class SecateurPanel(QDockWidget):
    def __init__(self, iface, parent=None):
        super().__init__("Ecosphères Secateur", parent or iface.mainWindow())
        self.iface = iface
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self._communes = []
        self._selected_code = None
        self._result_layers = []
        self._commune_name = None
        self._commune_geom = None
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

        # Buttons
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
        display = [f"{c['nom']} ({c['code']})" for c in self._communes]
        self._completer_model.setStringList(display)
        self._completer.complete()

    def _on_commune_selected(self, text):
        for c in self._communes:
            display = f"{c['nom']} ({c['code']})"
            if display == text:
                self._selected_code = c["code"]
                self._commune_name = c["nom"]
                self.run_button.setEnabled(True)
                self.status_label.setText(f"Commune sélectionnée : {c['nom']} ({c['code']})")
                return

    def _on_run(self):
        if not self._selected_code:
            return

        self.run_button.setEnabled(False)
        self.status_label.setText("Récupération de la géométrie de la commune…")
        self._force_repaint()

        geom = fetch_commune_geometry(self._selected_code)
        if geom is None or geom.isEmpty():
            self.status_label.setText("Erreur : impossible de récupérer la géométrie.")
            self.run_button.setEnabled(True)
            return

        self._commune_geom = geom

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

        results = intersect_commune(geom, layers, progress_callback=progress)

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

            export_results_to_pdf(
                self._result_layers,
                self._commune_name or "",
                self._commune_geom,
                path,
                progress_callback=progress,
            )
            self._finish_progress(f"Export PDF : {path}")
        except Exception as e:
            self._finish_progress(f"Erreur export PDF : {e}")

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
        from PyQt5.QtWidgets import QApplication

        QApplication.processEvents()
