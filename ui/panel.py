from qgis.gui import QgsMapLayerComboBox
from qgis.core import QgsProject, QgsVectorLayer, QgsMapLayer, QgsMapLayerProxyModel, QgsWkbTypes, QgsFeature
from qgis.PyQt.QtCore import QStringListModel, Qt, QTimer
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
from ..core.intersector import add_results_to_project, find_layers, intersect_layer, _get_group_by_path


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
        layout.addWidget(QLabel("Sélectionner l'objet à intersecter :"))

        #
        self.active_btn = QPushButton("Utiliser la géométrie active")
        self.active_btn.clicked.connect(self._use_active_layer_or_feature)
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

    def _on_basemap_selected(self, layer):
        if layer is None:
            self._selected_basemap = None
            self.status_label.setText("Fond de carte non sélectionné.")
            self.export_pdf_button.setEnabled(False)
            return

        self._selected_basemap = layer
        self.status_label.setText(f"Fond de carte sélectionné : {layer.name()}")
        self.export_pdf_button.setEnabled(True)

    def _use_active_layer_or_feature(self):
        """Retrieve the active vector layer or a single selected feature if exactly one is selected."""
        layer = self.iface.activeLayer()

        # Check that the active layer exists
        if layer is None:
            self.status_label.setText("Aucune couche active.")
            self.run_button.setEnabled(False)
            return

        # Check that the layer is a vector layer
        if not isinstance(layer, QgsVectorLayer):
            self.status_label.setText("La couche active n'est pas vectorielle.")
            self.run_button.setEnabled(False)
            return

        selected_features = layer.selectedFeatures()
        num_selected = len(selected_features)

        if num_selected == 1:
            # Exactly one feature selected: create a temporary memory layer with that feature
            feature = selected_features[0]

            # Crée ou réutilise une couche mémoire pour l'objet sélectionné
            layer_name = f"{layer.name()}_feature_{feature.id()}"
            project = QgsProject.instance()
            # Vérifier si une couche mémoire portant ce nom existe déjà
            existing_layers = project.mapLayersByName(layer_name)
            if existing_layers:
                # Réutiliser la couche existante
                mem_layer = existing_layers[0]
            else:
                # Crée une nouvelle couche mémoire avec le bon type géométrique et CRS
                geom_type = QgsWkbTypes.displayString(layer.wkbType())
                mem_layer = QgsVectorLayer(
                    f"{geom_type}?crs={layer.crs().authid()}",
                    layer_name,
                    "memory",
                )

                # Ajouter les champs de la couche source
                mem_layer.dataProvider().addAttributes(layer.fields())
                mem_layer.updateFields()

                # Cloner la feature pour éviter tout problème de référence
                new_feat = QgsFeature()
                new_feat.setGeometry(feature.geometry())
                new_feat.setAttributes(feature.attributes())

                # Ajouter la feature à la couche mémoire
                mem_layer.dataProvider().addFeature(new_feat)
                mem_layer.updateExtents()

                # Ajouter la couche au projet sans la placer à la racine
                project.addMapLayer(mem_layer, False)

                # S’assurer que le groupe "Objets créés" existe et y ajouter la couche
                group = _get_group_by_path(["Objets créés"])
                if group is None:
                    root = project.layerTreeRoot()
                    group = root.addGroup("Objets créés")
                # Insérer la couche dans le groupe (si déjà dans le groupe, l’insérer de nouveau n’a aucun effet)
                group.insertLayer(-1, mem_layer)

                self._selected_layer = mem_layer
                self._selected_feature = feature
                self.status_label.setText(
                    f"Objet ID {feature.id()} sélectionné dans {layer.name()} (couche temporaire prête)"
                )
                self.run_button.setEnabled(True)

        elif num_selected > 1:
            # Multiple features selected
            self._selected_layer = layer
            self._selected_feature = None
            self.status_label.setText(f"Plusieurs objets sélectionnés !")
            self.run_button.setEnabled(False)
        else:
            # No feature selected
            self._selected_layer = layer
            self._selected_feature = None
            self.status_label.setText(f"Active layer: {layer.name()}")
            self.run_button.setEnabled(True)

    # ---------------- PROCESS ---------------- #

    def _on_run(self):
        if self._selected_layer is None:
            return

        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group = root.findGroup('Résultats secateur')
        if group:
            group.removeAllChildren()
            root.removeChildNode(group)

        layers = find_layers(exclude=self._selected_layer)

        if not layers:
            self.status_label.setText("Aucune couche à comparer.")
            return

        self._start_progress(len(layers))

        def progress(current, total, name):
            self._update_progress(current, total, f"{current}/{total} : {name}")

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

            layer_count = max(len(results) - 1, 0)   # on enlève la couche source
            self._finish_progress(f"{layer_count} couches trouvées.")
        else:
            self._result_layers = []
            self.export_csv_button.setEnabled(False)
            self.export_pdf_button.setEnabled(False)
            self._finish_progress("Aucun résultat.")

    # ---------------- EXPORT ---------------- #

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
            export_results_to_pdf(
                self._result_layers,
                folder,
                progress_callback=self._update_progress,
                basemap_layer=self._selected_basemap,
            )

    def _verify_results_group(self):
        """Check if the 'Résultats secateur' group exists.

        If missing, update UI to show an error and disable export buttons.
        Returns True when the group is present, False otherwise.
        """
        root = QgsProject.instance().layerTreeRoot()
        if not root.findGroup('Résultats secateur'):
            self.status_label.setText('Aucun résultat Sécateur à exporter.')
            self.export_csv_button.setEnabled(False)
            self.export_pdf_button.setEnabled(False)
            return False
        return True

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
