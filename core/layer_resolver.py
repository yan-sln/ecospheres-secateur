from qgis.core import (
    QgsMapLayer,
    QgsProject,
    QgsVectorLayer,
)


class LayerResolver:
    @staticmethod
    def get(layer_id: str) -> QgsMapLayer | None:
        if not layer_id:
            return None

        return QgsProject.instance().mapLayer(layer_id)

    @staticmethod
    def get_vector(layer_id: str) -> QgsVectorLayer | None:
        layer = LayerResolver.get(layer_id)

        if isinstance(layer, QgsVectorLayer):
            return layer

        return None

    @staticmethod
    def get_many(layer_ids: list[str]) -> list[QgsMapLayer]:
        return [layer for lid in layer_ids if (layer := LayerResolver.get(lid)) is not None]

    @staticmethod
    def get_many_vectors(layer_ids: list[str]) -> list[QgsVectorLayer]:
        return [layer for lid in layer_ids if (layer := LayerResolver.get_vector(lid)) is not None]
