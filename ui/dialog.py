import json

from qgis.PyQt.QtCore import Qt, QTimer, QStringListModel
from qgis.PyQt.QtWidgets import (
    QCompleter,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..core.commune_api import fetch_commune_geometry, search_communes
from ..core.export import export_results_to_csv, export_results_to_pdf
from ..core.intersector import add_results_to_project, find_wfs_layers, intersect_commune


class SecateurDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle("Ecosphères Secateur")
        self.setMinimumWidth(400)

        self._communes = []  # current autocomplete results
        self._selected_code = None
        self._result_layers = []  # last intersection results
        self._commune_name = None
        self._commune_geom = None
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._do_search)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

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

        # Status
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def _on_text_changed(self, text):
        self._selected_code = None
        self.run_button.setEnabled(False)
        if len(text) >= 2:
            self._debounce_timer.start()
        else:
            self._completer_model.setStringList([])

    def _do_search(self):
        text = self.search_input.text().strip()
        if len(text) < 2:
            return
        self._communes = search_communes(text)
        display = [f"{c['nom']} ({c['code']})" for c in self._communes]
        self._completer_model.setStringList(display)
        self._completer.complete()

    def _on_commune_selected(self, text):
        # Parse "Dijon (21231)" back to code
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

        self.status_label.setText(f"Intersection avec {len(layers)} couche(s) WFS…")
        self._force_repaint()

        def progress(current, total, name):
            if current < total:
                self.status_label.setText(f"Intersection {current + 1}/{total} : {name}")
                self._force_repaint()

        results = intersect_commune(geom, layers, progress_callback=progress)

        if results:
            add_results_to_project(results)
            self._result_layers = results
            self.export_csv_button.setEnabled(True)
            self.export_pdf_button.setEnabled(True)
            total_feats = sum(r.featureCount() for r in results)
            self.status_label.setText(
                f"Terminé — {total_feats} entité(s) trouvée(s) dans {len(results)} couche(s)."
            )
        else:
            self._result_layers = []
            self.export_csv_button.setEnabled(False)
            self.export_pdf_button.setEnabled(False)
            self.status_label.setText("Aucune intersection trouvée.")

        self.run_button.setEnabled(True)

    def _on_export_csv(self):
        if not self._result_layers:
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Dossier d'export CSV"
        )
        if not folder:
            return
        try:
            def progress(current, total, name):
                self.status_label.setText(f"Export CSV {current + 1}/{total} : {name}")
                self._force_repaint()

            written = export_results_to_csv(self._result_layers, folder, progress)
            self.status_label.setText(f"Export CSV : {len(written)} fichier(s) dans {folder}")
        except Exception as e:
            self.status_label.setText(f"Erreur export CSV : {e}")

    def _on_export_pdf(self):
        if not self._result_layers:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter le rapport PDF", "", "PDF (*.pdf)",
            options=QFileDialog.Options(),
        )
        if not path:
            return
        try:
            def progress(current, total, name):
                self.status_label.setText(f"Export PDF {current + 1}/{total} : {name}")
                self._force_repaint()

            export_results_to_pdf(
                self._result_layers, self._commune_name, self._commune_geom, path,
                progress_callback=progress,
            )
            self.status_label.setText(f"Export PDF : {path}")
        except Exception as e:
            self.status_label.setText(f"Erreur export PDF : {e}")

    def _force_repaint(self):
        from qgis.PyQt.QtWidgets import QApplication
        QApplication.processEvents()
