from dataclasses import dataclass
from typing import Literal

from qgis.core import (
    QgsFeature,
    QgsProcessingFeedback,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsWkbTypes,
)

from ..core.constants import CREATED_OBJECTS_GROUP_NAME, RESULT_GROUP_NAME
from ..core.intersector import add_results_to_project, intersect_layer
from ..core.utils import find_layers, get_created_objects_group, get_results_group

# ──────────────────────────────────────────────
#  Service result objects (explicit contracts)
# ──────────────────────────────────────────────
Level = Literal["info", "warning", "error"]


@dataclass
class SelectionResult:
    layer: QgsVectorLayer | None
    feature: QgsFeature | None
    message: str
    level: Level

    def __post_init__(self):
        assert self.level in ("info", "warning", "error")
        if self.layer is not None:
            assert isinstance(self.layer, QgsVectorLayer)
        if self.feature is not None:
            assert isinstance(self.feature, QgsFeature)


@dataclass
class ProcessResult:
    result_layers: list[QgsVectorLayer]
    message: str
    level: Level

    def __post_init__(self):
        assert isinstance(self.result_layers, list)
        assert all(isinstance(L, QgsVectorLayer) for L in self.result_layers)


# ──────────────────────────────────────────────
#  SecateurService (NO UI)
# ──────────────────────────────────────────────


class SecateurService:
    """
    Service métier.
    Ne contient AUCUNE dépendance UI (Qt).
    Conserve tous les effets de bord QGIS existants.
    """

    def get_available_raster_layers(self):
        """Get all raster layers available in the current project."""
        return [lyr for lyr in QgsProject.instance().mapLayers().values() if isinstance(lyr, QgsRasterLayer)]

    # ──────────────────────────────────────────────
    #  Selection
    # ──────────────────────────────────────────────

    def select(self, iface) -> SelectionResult:
        layer = iface.activeLayer()

        if layer is None:
            return SelectionResult(None, None, "Aucune entité active.", "warning")

        if not isinstance(layer, QgsVectorLayer):
            return SelectionResult(None, None, "Sélection réinitialisée (pas de couche vectorielle).", "warning")

        results_group = get_results_group()
        if results_group is None:
            return SelectionResult(None, None, f"Impossible d'accéder au groupe {RESULT_GROUP_NAME}.", "error")

        if results_group.findLayer(layer.id()) is not None:
            return SelectionResult(None, None, f"La sélection appartient au groupe {RESULT_GROUP_NAME}.", "warning")

        selected = layer.selectedFeatures()

        if len(selected) == 1:
            return self._select_single_feature(layer, selected[0])

        if len(selected) > 1:
            return SelectionResult(layer, None, "Plusieurs objets sélectionnés !", "warning")

        return SelectionResult(layer, None, f"Couche sélectionnée : {layer.name()}", "info")

    def _select_single_feature(self, layer, feature) -> SelectionResult:
        mem_layer = self._create_memory_layer_from_feature(layer, feature)

        group = get_created_objects_group()
        if group is None:
            return SelectionResult(
                mem_layer,
                feature,
                f"Impossible d'ajouter la couche : groupe '{CREATED_OBJECTS_GROUP_NAME}' introuvable.",
                "error",
            )

        group.insertLayer(-1, mem_layer)
        return SelectionResult(mem_layer, feature, "", "info")

    # ──────────────────────────────────────────────
    #  Process
    # ──────────────────────────────────────────────

    def run(self, selected_layer: QgsVectorLayer, feedback: QgsProcessingFeedback) -> ProcessResult:
        group = get_results_group(clear=True)
        if group is None:
            return ProcessResult([], "Impossible d'accéder au groupe 'Résultats secateur'.", "error")

        layers = find_layers(exclude=selected_layer)
        if not layers:
            return ProcessResult([], "Aucune couche visible à comparer.", "error")

        results = intersect_layer(
            selected_layer,
            layers,
            feedback=feedback,
        )

        if results:
            add_results_to_project(results)

            self._cleanup_created_objects_group()

            layer_count = max(len(results) - 1, 0)
            return ProcessResult(results, f"{layer_count} couches trouvées.", "info")

        return ProcessResult([], "Aucun résultat.", "info")

    def _cleanup_created_objects_group(self):
        objs_group = get_created_objects_group(clear=True)
        if objs_group is not None:
            QgsProject.instance().layerTreeRoot().removeChildNode(objs_group)

    # ──────────────────────────────────────────────
    #  Memory layer
    # ──────────────────────────────────────────────

    def _create_memory_layer_from_feature(self, source_layer: QgsVectorLayer, feature: QgsFeature) -> QgsVectorLayer:
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
